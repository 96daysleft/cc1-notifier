"""WebSocket client for Centauri Carbon SDCP protocol, inspired by OctoEverywhere's implementation."""

import asyncio
import json
import ssl
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

import websockets

from .alert_processor import AlertProcessor
from .config import config, logger
from .models.attributes import AttributesMessage
from .models.notice import Alert


# SDCP topic constants
def _topic(path: str) -> str:
    return f"sdcp/{path}/{config.mainboard_id}"


TOPIC_STATUS = lambda: _topic("status")
TOPIC_NOTICE = lambda: _topic("notice")
TOPIC_RESPONSE = lambda: _topic("response")
TOPIC_ERROR = lambda: _topic("error")
TOPIC_REQUEST = lambda: _topic("request")
TOPIC_ATTRIBUTES = lambda: _topic("attributes")


class CentauriWebSocketClient:
    """
    WebSocket client for the Centauri Carbon SDCP API.

    Protocol details:
    - URL:       ws://{ip}:3030/websocket
    - Heartbeat: send text "ping", expect text "pong" back
    - Messages:  JSON with a "Topic" field for routing (sdcp/status, sdcp/notice, etc.)
    - Requests:  JSON with Topic=sdcp/request/{MainboardID} and a Data.Cmd field

    Alert logic is handled entirely by AlertProcessor — this class only manages
    the connection lifecycle and dispatches raw messages.
    """

    RECONNECT_DELAY_SECS = 10
    # NOTE: ping_interval is disabled — the SDCP protocol uses text "ping"/"pong",
    # NOT WebSocket protocol-level ping frames.

    def __init__(self):
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.is_connected: bool = False
        self.is_running: bool = False
        self.reconnect_attempts: int = 0

        # All alert decisions and buffering live here
        self.alert_processor = AlertProcessor()

        # Callbacks (OctoEverywhere on_open / on_close / on_error style)
        self.on_connect: Optional[Callable[[], None]] = None
        self.on_disconnect: Optional[Callable[[Optional[Exception]], None]] = None
        self.on_error: Optional[Callable[[Exception], None]] = None
        self.on_message: Optional[Callable[[Dict[str, Any]], None]] = None

    # ------------------------------------------------------------------
    # URL
    # ------------------------------------------------------------------

    @property
    def url(self) -> str:
        """Build the SDCP WebSocket URL: ws://{ip}:3030/websocket"""
        ip = config.centauri_ip.replace("ws://", "").replace("wss://", "")
        return f"ws://{ip}:{config.centauri_port}/websocket"

    def _make_ssl_context(self) -> Optional[ssl.SSLContext]:
        if not self.url.startswith("wss://"):
            return None
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def test_connection(self) -> bool:
        """Quick connectivity check — connect then immediately close."""
        try:
            logger.info("Testing WebSocket connection", url=self.url)
            async with websockets.connect(self.url, ssl=self._make_ssl_context(), open_timeout=5):
                logger.info("WebSocket test connection successful")
                return True
        except Exception as e:
            logger.warning("WebSocket test connection failed", error=str(e))
            return False

    async def get_new_alerts(self) -> List[Alert]:
        """Drain and return all buffered alerts. Delegates to AlertProcessor."""
        return await self.alert_processor.get_new_alerts()

    async def send_heartbeat(self) -> bool:
        """Send a text 'ping' — SDCP heartbeat (not a WS protocol ping frame)."""
        if not self.is_connected or not self.ws:
            return False
        try:
            await self.ws.send("ping")
            logger.debug("Heartbeat ping sent")
            return True
        except Exception as e:
            logger.debug("Heartbeat ping failed", error=str(e))
            return False

    def stop(self) -> None:
        self.is_running = False

    async def disconnect(self, reason: str = "Manual disconnect") -> None:
        self.is_running = False
        self.is_connected = False
        if self.ws:
            logger.info("Disconnecting from Centauri WebSocket", reason=reason)
            try:
                await self.ws.close()
            except Exception:
                pass
            self.ws = None

    # ------------------------------------------------------------------
    # Reconnect loop
    # ------------------------------------------------------------------

    async def start_with_reconnect(self) -> None:
        """Connect and auto-reconnect on any failure."""
        self.is_running = True

        while self.is_running:
            try:
                logger.info(
                    "Connecting to Centauri WebSocket",
                    url=self.url,
                    attempt=self.reconnect_attempts + 1,
                )

                async with websockets.connect(
                    self.url,
                    ssl=self._make_ssl_context(),
                    # ping_interval intentionally None — SDCP uses text ping/pong
                    ping_interval=None,
                ) as ws:
                    self.ws = ws
                    self.is_connected = True
                    self.reconnect_attempts = 0

                    logger.info("Connected to Centauri WebSocket")
                    await self._request_status()

                    if self.on_connect:
                        self.on_connect()

                    async for raw in ws:
                        await self._handle_message(raw)

                logger.info("WebSocket connection closed by server")
                if self.on_disconnect:
                    self.on_disconnect(None)

            except websockets.exceptions.ConnectionClosed as e:
                logger.info("WebSocket connection closed", code=e.code, reason=e.reason)
                if self.on_disconnect:
                    self.on_disconnect(e)
            except Exception as e:
                logger.error("WebSocket error", error=str(e))
                if self.on_error:
                    self.on_error(e)
            finally:
                self.is_connected = False
                self.ws = None

            if not self.is_running:
                break

            self.reconnect_attempts += 1
            logger.info("Reconnecting", delay_secs=self.RECONNECT_DELAY_SECS, attempt=self.reconnect_attempts)
            await asyncio.sleep(self.RECONNECT_DELAY_SECS)

    # ------------------------------------------------------------------
    # SDCP protocol helpers
    # ------------------------------------------------------------------

    def _build_request(self, cmd: int, data: Dict[str, Any] = None) -> str:
        """Build an SDCP request envelope."""
        return json.dumps({
            "Id": str(uuid.uuid4()),
            "Data": {
                "Cmd": cmd,
                "Data": data or {},
                "RequestID": str(uuid.uuid4()),
                "MainboardID": config.mainboard_id,
                "TimeStamp": int(time.time()),
                "From": 0,
            },
            "Topic": TOPIC_REQUEST(),
        })

    async def _request_status(self) -> None:
        """Request current machine status on connect (Cmd=0)."""
        if self.ws:
            await self.ws.send(self._build_request(cmd=0))
            logger.info("Status request sent", mainboard_id=config.mainboard_id)

    # ------------------------------------------------------------------
    # Message dispatch
    # ------------------------------------------------------------------

    async def _handle_message(self, raw: str) -> None:
        # SDCP heartbeat — plain text, not JSON
        if raw == "pong":
            logger.debug("Heartbeat pong received")
            return

        try:
            msg = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse WebSocket message", error=str(e), raw=raw[:200])
            return

        topic: str = msg.get("Topic", "")
        logger.debug("WebSocket message received", topic=topic)

        if topic == TOPIC_STATUS():
            logger.debug('topic status')
            await self.alert_processor.process_status(msg)
        elif topic == TOPIC_NOTICE():
            logger.debug('topic notice')
            await self.alert_processor.process_notice(msg)
        elif topic == TOPIC_ERROR():
            logger.debug('topic error')
            logger.error("SDCP server error", data=msg.get("Data", {}))
            await self.alert_processor.process_error(msg)
        elif topic == TOPIC_RESPONSE():
            logger.debug('topic response')
            await self.alert_processor.process_response(msg)
        elif topic == TOPIC_ATTRIBUTES():
            logger.debug('topic attributes')
            await self._handle_attributes(msg)
        else:
            logger.debug("Unknown topic", topic=topic)

        if self.on_message:
            self.on_message(msg)

    async def _handle_attributes(self, msg: Dict[str, Any]) -> None:
        """Handle sdcp/attributes messages — log machine identity and capabilities."""
        try:
            attrs_msg = AttributesMessage.model_validate(msg)
        except Exception as e:
            logger.error("Failed to parse attributes message", error=str(e), raw=msg)
            return

        logger.debug("Attributes raw", raw=json.dumps(msg, indent=2))

        a = attrs_msg.Attributes
        logger.info(
            "Machine attributes",
            machine=a.MachineName,
            brand=a.BrandName,
            firmware=a.FirmwareVersion,
            protocol=a.ProtocolVersion,
            size=a.XYZsize,
            ip=a.MainboardIP,
        )
