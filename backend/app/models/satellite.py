from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class TLE(BaseModel):
    name: str
    norad_id: int
    line1: str
    line2: str
    fetched_at: datetime


class SatellitePosition(BaseModel):
    norad_id: int
    name: str
    lat: float
    lng: float
    alt_km: float
    az_deg: float
    el_deg: float
    ra_deg: float
    dec_deg: float
    timestamp: datetime


class SatellitePass(BaseModel):
    norad_id: int
    name: str
    start_utc: datetime
    end_utc: datetime
    max_el_deg: float
    start_az_deg: float
    end_az_deg: float
    duration_s: int
    mag: Optional[float] = None


class GroundTrackPoint(BaseModel):
    lat: float
    lng: float
    timestamp: datetime
    alt_km: float
    el_deg: Optional[float] = None   # elevation from observer (None = not computed)
    visible: bool = False             # True if above observer's horizon


class TrackingFeasibility(BaseModel):
    feasible: bool
    target: str
    peak_rate_arcsec_s: float
    mount_max_rate_arcsec_s: float
    recommendation: str


class SatelliteCategory(BaseModel):
    id: int
    name: str
    description: str = ""
