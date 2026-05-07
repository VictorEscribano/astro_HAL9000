from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from enum import Enum


class TrackingRate(str, Enum):
    SIDEREAL = "sidereal"
    LUNAR = "lunar"
    SOLAR = "solar"
    CUSTOM = "custom"


class MountStatus(BaseModel):
    ra_h: float = 0.0
    dec_deg: float = 0.0
    alt_deg: float = 0.0
    az_deg: float = 0.0
    tracking: bool = False
    tracking_rate: Optional[TrackingRate] = None
    target_name: Optional[str] = None
    slewing: bool = False
    parked: bool = True
    log: List[str] = []


class SlewCommand(BaseModel):
    ra_h: Optional[float] = None
    dec_deg: Optional[float] = None
    alt_deg: Optional[float] = None
    az_deg: Optional[float] = None
    target_name: Optional[str] = None
    tracking_rate: TrackingRate = TrackingRate.SIDEREAL


class MountCommandResult(BaseModel):
    success: bool
    command_strings: List[str]
    message: str
    timestamp: datetime
