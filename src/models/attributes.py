"""Pydantic models for the SDCP sdcp/attributes WebSocket message."""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class DevicesStatus(BaseModel):
    model_config = ConfigDict(extra='ignore')

    ZMotorStatus: Optional[int] = None
    YMotorStatus: Optional[int] = None
    XMotorStatus: Optional[int] = None
    ExtruderMotorStatus: Optional[int] = None


class AttributesPayload(BaseModel):
    model_config = ConfigDict(extra='ignore')

    Name: Optional[str] = None
    MachineName: Optional[str] = None
    BrandName: Optional[str] = None
    ProtocolVersion: Optional[str] = None
    FirmwareVersion: Optional[str] = None
    XYZsize: Optional[str] = None              # e.g. "300x300x400"
    MainboardIP: Optional[str] = None
    MainboardID: Optional[str] = None
    MainboardMAC: Optional[str] = None
    NetworkStatus: Optional[str] = None        # e.g. "wlan"
    UsbDiskStatus: Optional[int] = None
    CameraStatus: Optional[int] = None
    RemainingMemory: Optional[int] = None      # bytes
    SDCPStatus: Optional[int] = None
    NumberOfVideoStreamConnected: Optional[int] = None
    MaximumVideoStreamAllowed: Optional[int] = None
    NumberOfCloudSDCPServicesConnected: Optional[int] = None
    MaximumCloudSDCPSercicesAllowed: Optional[int] = None  # firmware typo preserved
    Capabilities: Optional[List[str]] = None
    SupportFileType: Optional[List[str]] = None
    devices_status: Optional[DevicesStatus] = Field(None, alias='DevicesStatus')


class AttributesMessage(BaseModel):
    """Full sdcp/attributes/{MainboardID} WebSocket message envelope."""
    Attributes: AttributesPayload
    MainboardID: str
    TimeStamp: int
    Topic: str
