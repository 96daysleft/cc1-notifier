"""Pydantic model for application configuration."""

from typing import Literal
from pydantic import BaseModel, Field


class Config(BaseModel):
    centauri_ip: str = Field(default="192.168.45.245")
    centauri_port: int = Field(default=3030)        # SDCP WebSocket port
    mainboard_id: str = Field(default="")           # Required for SDCP topic routing
    discord_webhook_url: str = ""
    poll_interval_minutes: int = Field(default=5, ge=1)
    max_alerts_per_poll: int = Field(default=10, ge=1)
    log_level: Literal['DEBUG', 'INFO', 'WARNING', 'ERROR'] = 'INFO'
    skip_initial_connection_test: bool = True
    notify_on_start: bool = True      # alert when status transitions to Printing
    notify_on_shutdown: bool = True   # alert when status transitions to Idle (print done / shutdown)
