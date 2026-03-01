"""Pydantic models for the SDCP sdcp/status and sdcp/response WebSocket messages."""

from enum import IntEnum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field


class MachineStatus(IntEnum):
    """Machine status codes reported in CurrentStatus / PreviousStatus fields."""
    IDLE = 0
    PRINTING = 1
    FILE_TRANSFERRING = 2
    CALIBRATING = 3
    DEVICE_TESTING = 4

    @classmethod
    def label(cls, code: int) -> str:
        try:
            return cls(code).name.replace("_", " ").title()
        except ValueError:
            return f"Unknown ({code})"


MACHINE_STATUS_COLORS = {
    MachineStatus.IDLE: 0x808080,
    MachineStatus.PRINTING: 0x00aaff,
    MachineStatus.FILE_TRANSFERRING: 0xffaa00,
    MachineStatus.CALIBRATING: 0xaa00ff,
    MachineStatus.DEVICE_TESTING: 0xffff00,
}

MACHINE_STATUS_EMOJIS = {
    MachineStatus.IDLE: '⚪',
    MachineStatus.PRINTING: '🖨️',
    MachineStatus.FILE_TRANSFERRING: '📁',
    MachineStatus.CALIBRATING: '🔧',
    MachineStatus.DEVICE_TESTING: '🔬',
}


class FanSpeed(BaseModel):
    model_config = ConfigDict(extra='ignore')

    ModelFan: Optional[int] = None
    ModeFan: Optional[int] = None
    AuxiliaryFan: Optional[int] = None
    BoxFan: Optional[int] = None


class LightStatus(BaseModel):
    model_config = ConfigDict(extra='ignore')

    SecondLight: Optional[int] = None
    RgbLight: Optional[List[int]] = None  # [R, G, B]


class PrintInfo(BaseModel):
    # extra='ignore' swallows the null-terminated hex-string keys the firmware emits
    model_config = ConfigDict(extra='ignore')

    Status: Optional[int] = None
    CurrentLayer: Optional[int] = None
    TotalLayer: Optional[int] = None
    CurrentTicks: Optional[float] = None   # elapsed seconds (firmware sends float)
    TotalTicks: Optional[float] = None     # estimated total seconds
    Filename: Optional[str] = None
    ErrorNumber: Optional[int] = None
    TaskId: Optional[str] = None
    PrintSpeedPct: Optional[int] = None    # actual field name in firmware
    Progress: Optional[int] = None

    @property
    def layer_progress_pct(self) -> Optional[int]:
        """Progress 0-100 derived from layer count (more reliable than Progress field)."""
        if self.TotalLayer and self.CurrentLayer is not None:
            return int(self.CurrentLayer / self.TotalLayer * 100)
        return None


class StatusPayload(BaseModel):
    # extra='ignore' handles firmware-specific fields like TimeLapseStatus, PlatFormType
    model_config = ConfigDict(extra='ignore', populate_by_name=True)

    CurrentStatus: Optional[List[int]] = None
    # PreviousStatus can be int or list depending on firmware version
    PreviousStatus: Optional[Union[int, List[int]]] = None

    TempOfNozzle: Optional[float] = None
    TempTargetNozzle: Optional[float] = None
    TempOfHotbed: Optional[float] = None
    TempTargetHotbed: Optional[float] = None
    TempOfBox: Optional[float] = None
    TempTargetBox: Optional[float] = None

    # "202.00,264.50,22.57" — comma-separated X,Y,Z string
    CurrenCoord: Optional[str] = None

    CurrentFanSpeed: Optional[FanSpeed] = None
    light_status: Optional[LightStatus] = Field(None, alias='LightStatus')
    ZOffset: Optional[float] = None
    PrintSpeed: Optional[int] = None
    print_info: Optional[PrintInfo] = Field(None, alias='PrintInfo')

    @property
    def current_status_labels(self) -> List[str]:
        return [MachineStatus.label(c) for c in (self.CurrentStatus or [])]

    @property
    def previous_status_labels(self) -> List[str]:
        prev = self.PreviousStatus
        if prev is None:
            return []
        codes = prev if isinstance(prev, list) else [prev]
        return [MachineStatus.label(p) for p in codes]


class StatusMessage(BaseModel):
    """Full sdcp/status/{MainboardID} WebSocket message envelope."""
    Status: StatusPayload
    MainboardID: str
    TimeStamp: int
    Topic: str


class ResponseData(BaseModel):
    """The 'Data' object inside an sdcp/response envelope.

    For Cmd=0 (GetCurrentStatus) the inner Data field contains a 'Status' key
    with the same payload as a pushed sdcp/status message.
    """
    Cmd: int
    Data: Dict[str, Any]   # varies by Cmd; for Cmd=0 contains {"Status": {...}}
    RequestID: Optional[str] = None
    MainboardID: Optional[str] = None
    TimeStamp: Optional[int] = None
    From: Optional[int] = None

    def status_payload(self) -> Optional[StatusPayload]:
        """Extract and validate the StatusPayload for Cmd=0 responses."""
        raw = self.Data.get("Status")
        if raw is None:
            return None
        return StatusPayload.model_validate(raw)


class ResponseMessage(BaseModel):
    """Full sdcp/response/{MainboardID} WebSocket message envelope."""
    Id: Optional[str] = None
    Data: ResponseData
    Topic: str
