"""Determines when to generate alerts based on incoming SDCP messages.

This module owns all stateful alert logic:
- tracking last known status / progress so changes can be detected
- deciding which events are worth alerting on
- building Alert objects and buffering them for the poll loop to drain

CentauriWebSocketClient calls process_status() and process_notice() after
parsing raw WebSocket messages; it does not make any alerting decisions itself.
"""

import asyncio
import json
import time
import uuid
from typing import Any, Dict, List, Optional

from .config import config, logger
from .models.notice import Alert
from .models.status import MachineStatus, StatusMessage


class AlertProcessor:
    """Stateful processor that decides when to fire alerts.

    Receives raw SDCP message dicts from the WebSocket client,
    parses them, logs relevant fields, and buffers Alert objects
    whenever something noteworthy happens.
    """

    def __init__(self):
        self._alert_buffer: List[Alert] = []
        self._buffer_lock = asyncio.Lock()

        # Retained between messages to detect changes
        self._last_current_status: Optional[List[int]] = None
        self._last_progress: Optional[int] = None

    # ------------------------------------------------------------------
    # Public API (called by service poll loop)
    # ------------------------------------------------------------------

    async def get_new_alerts(self) -> List[Alert]:
        """Drain and return all buffered alerts (thread-safe)."""
        async with self._buffer_lock:
            alerts = self._alert_buffer.copy()
            self._alert_buffer.clear()
            return alerts

    # ------------------------------------------------------------------
    # Message processors (called by CentauriWebSocketClient)
    # ------------------------------------------------------------------

    async def process_status(self, msg: Dict[str, Any]) -> None:
        """Process an sdcp/status message.

        Logs machine state and buffers alerts for:
        - Initial status on first message after connect
        - Status transitions (e.g. Idle → Printing)
        - Print progress milestones (25 %, 50 %, 75 %)
        """
        try:
            status_msg = StatusMessage.model_validate(msg)
        except Exception as e:
            logger.error("Failed to parse status message", error=str(e), raw=msg)
            return

        s = status_msg.Status

        logger.info(
            "Machine status",
            current=s.current_status_labels,
            previous=s.previous_status_labels,
            print_status=s.print_status_label,
            nozzle_temp=s.TempOfNozzle,
            nozzle_target=s.TempTargetNozzle,
            bed_temp=s.TempOfHotbed,
            bed_target=s.TempTargetHotbed,
            print_file=s.print_info.Filename if s.print_info else None,
            layer=f"{s.print_info.CurrentLayer}/{s.print_info.TotalLayer}" if s.print_info else None,
            progress=s.print_info.Progress if s.print_info else None,
            speed_pct=s.print_info.PrintSpeedPct if s.print_info else None,
            elapsed=s.print_info.CurrentTicks if s.print_info else None,
            eta=s.print_info.TotalTicks if s.print_info else None,
        )

        if s.print_info:
            logger.debug(
                "PrintInfo raw",
                print_info=s.print_info.model_dump(),
            )

        await self._check_status_change(s, status_msg.TimeStamp)
        await self._check_progress_milestones(s, status_msg.TimeStamp)

    async def process_response(self, msg: Dict[str, Any]) -> None:
        """Process an sdcp/response message.

        Responses are command acknowledgments. Logs the result and buffers an
        alert only when the response indicates a failure (Result != 0).
        """
        data = msg.get("Data", {}).get("Data", {})
        cmd = msg.get("Data", {}).get("Cmd")
        result = data.get("Result", 0)

        logger.debug("SDCP response received", cmd=cmd, result=result, data=data)

        if result != 0:
            alert = Alert(
                id=msg.get("Id", str(uuid.uuid4())),
                title="SDCP Command Failed",
                description=f"Command {cmd} failed with result code {result}.",
                severity="high",
                timestamp=str(int(time.time())),
                source="sdcp/response",
                details=data,
            )
            async with self._buffer_lock:
                self._alert_buffer.append(alert)
            logger.warning("Command failure alert buffered", cmd=cmd, result=result)

    async def process_error(self, msg: Dict[str, Any]) -> None:
        """Process an sdcp/error message — buffer as a high-severity alert."""
        data = msg.get("Data", {})
        alert = Alert(
            id=msg.get("Id", str(uuid.uuid4())),
            title="SDCP Server Error",
            description=json.dumps(data) if data else "An SDCP server error was reported.",
            severity="high",
            timestamp=str(int(time.time())),
            source="sdcp/error",
            details=data if data else None,
        )
        async with self._buffer_lock:
            self._alert_buffer.append(alert)
        logger.info("Error alert buffered", id=alert.id, data=data)

    async def process_notice(self, msg: Dict[str, Any]) -> None:
        """Process an sdcp/notice message — buffer directly as an alert."""
        data = msg.get("Data", {}).get("Data", {})
        try:
            alert = Alert(
                id=msg.get("Id", str(uuid.uuid4())),
                title=data.get("Title", "Centauri Notice"),
                description=data.get("Message", json.dumps(data)),
                severity=_map_severity(data.get("Level", 0)),
                timestamp=data.get("Timestamp", str(int(time.time()))),
                source=data.get("Source"),
                details=data,
            )
            async with self._buffer_lock:
                self._alert_buffer.append(alert)
            logger.info("Notice buffered", id=alert.id, severity=alert.severity, title=alert.title[:60])
        except Exception as e:
            logger.error("Failed to parse notice", error=str(e), data=data)

    # ------------------------------------------------------------------
    # Internal alert rules
    # ------------------------------------------------------------------

    async def _check_status_change(self, s, timestamp: int) -> None:
        """Buffer an alert if the machine status has changed since last message."""
        current_status = s.CurrentStatus or []

        if self._last_current_status is None:
            # First status received after connect — report current state
            curr = ", ".join(MachineStatus.label(c) for c in current_status) or "Unknown"
            parts = [f"Status: {curr}"]
            if s.print_info and s.print_info.Filename:
                parts.append(f"File: {s.print_info.Filename}")
                if s.print_info.layer_progress_pct is not None:
                    parts.append(f"Progress: {s.print_info.layer_progress_pct}%")
            await self._buffer(Alert(
                id=str(uuid.uuid4()),
                title="Current Machine Status",
                description="\n".join(parts),
                severity="low",
                timestamp=str(timestamp),
                source="sdcp/status",
            ))
            logger.info("Initial status alert buffered", status=curr)

        elif current_status != self._last_current_status:
            prev_codes = self._last_current_status
            prev = ", ".join(MachineStatus.label(c) for c in prev_codes)
            curr = ", ".join(MachineStatus.label(c) for c in current_status)

            is_start = MachineStatus.PRINTING in current_status and MachineStatus.PRINTING not in prev_codes
            is_shutdown = MachineStatus.IDLE in current_status and MachineStatus.IDLE not in prev_codes

            if is_start and config.notify_on_start:
                desc_parts = ["Printer has started a new job."]
                if s.print_info and s.print_info.Filename:
                    desc_parts.append(f"File: {s.print_info.Filename}")
                await self._buffer(Alert(
                    id=str(uuid.uuid4()),
                    title="Print Started",
                    description="\n".join(desc_parts),
                    severity="low",
                    timestamp=str(timestamp),
                    source="sdcp/status",
                ))
                logger.info("Print start alert buffered")
            elif is_shutdown and config.notify_on_shutdown:
                await self._buffer(Alert(
                    id=str(uuid.uuid4()),
                    title="Printer Idle / Shutdown",
                    description=f"Status changed from {prev} to {curr}",
                    severity="low",
                    timestamp=str(timestamp),
                    source="sdcp/status",
                ))
                logger.info("Shutdown alert buffered", prev=prev, curr=curr)
            elif not is_start and not is_shutdown:
                await self._buffer(Alert(
                    id=str(uuid.uuid4()),
                    title="Machine Status Changed",
                    description=f"Status changed from {prev} to {curr}",
                    severity="low",
                    timestamp=str(timestamp),
                    source="sdcp/status",
                ))
                logger.info("Status change alert buffered", prev=prev, curr=curr)

        self._last_current_status = current_status

    async def _check_progress_milestones(self, s, timestamp: int) -> None:
        """Buffer an alert when layer progress crosses 25 %, 50 %, or 75 %."""
        if s.print_info is None:
            return

        # Firmware Progress field is often stuck at 0; use layer-derived value
        progress = s.print_info.Progress
        if progress is None:
            return

        for milestone in (25, 50, 75):
            if self._last_progress is not None and self._last_progress < milestone and progress >= milestone:
                await self._buffer(Alert(
                    id=str(uuid.uuid4()),
                    title=f"Print {milestone}% Complete",
                    description=(
                        f"{s.print_info.Filename or 'Print'} is {milestone}% complete "
                        f"({s.print_info.CurrentLayer}/{s.print_info.TotalLayer} layers)"
                    ),
                    severity="low",
                    timestamp=str(timestamp),
                    source="sdcp/status",
                ))
                logger.info("Progress milestone alert buffered", milestone=milestone, progress=progress)

        self._last_progress = progress

    async def _buffer(self, alert: Alert) -> None:
        async with self._buffer_lock:
            self._alert_buffer.append(alert)


def _map_severity(level: int) -> str:
    """Map a numeric SDCP notice level to an Alert severity string."""
    return {0: "low", 1: "medium", 2: "high", 3: "critical"}.get(level, "low")
