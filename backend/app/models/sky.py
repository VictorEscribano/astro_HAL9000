from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class Observer(BaseModel):
    lat: float
    lng: float
    alt_m: float = 0.0
    name: str = "Observer"


class SkyObject(BaseModel):
    name: str
    catalog_id: Optional[str] = None
    object_type: str
    ra_h: Optional[float] = None        # RA in decimal hours
    dec_deg: Optional[float] = None     # Dec in decimal degrees
    alt_deg: Optional[float] = None
    az_deg: Optional[float] = None
    magnitude: Optional[float] = None
    angular_size_arcmin: Optional[float] = None
    rise_utc: Optional[datetime] = None
    set_utc: Optional[datetime] = None
    transit_utc: Optional[datetime] = None
    transit_alt: Optional[float] = None
    note: Optional[str] = None


class MoonInfo(BaseModel):
    phase: float               # 0.0 = new, 0.5 = full, 1.0 = new again
    illumination_pct: float
    phase_name: str
    alt_deg: Optional[float] = None
    az_deg: Optional[float] = None
    rise_utc: Optional[datetime] = None
    set_utc: Optional[datetime] = None
    transit_utc: Optional[datetime] = None
    angular_diameter_arcmin: float
    interference: bool = False
    interference_note: str = ""


class ObjectPosition(BaseModel):
    name: str
    ra_h: float
    dec_deg: float
    alt_deg: float
    az_deg: float
    rise_utc: Optional[datetime] = None
    set_utc: Optional[datetime] = None
    transit_utc: Optional[datetime] = None
    transit_alt: Optional[float] = None
    angular_size_arcmin: Optional[float] = None
    distance_au: Optional[float] = None
    above_horizon: bool = False
