"""Pydantic models for the SDCP sdcp/notice topic and internal alert representation."""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel


class Alert(BaseModel):
    """Internal representation of a Centauri notice/alert."""
    id: str
    title: str
    description: str
    severity: Literal['low', 'medium', 'high', 'critical']
    timestamp: str
    source: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class CentauriApiResponse(BaseModel):
    """Response format from Centauri API."""
    success: bool
    data: List[Alert]
    timestamp: str
