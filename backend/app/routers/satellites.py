"""Satellite endpoints."""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional

from app.tools.satellites import (
    get_satellite_ground_track, get_satellite_position_now,
    get_satellite_passes, get_satellites_overhead, check_tracking_feasibility,
    get_satellite_footprint,
)
from app.services.n2yo import SATELLITE_CATEGORIES
from app.services.satcat import search_satellites
from app.models.satellite import SatellitePosition, SatellitePass, GroundTrackPoint, TrackingFeasibility, SatelliteCategory

router = APIRouter(prefix="/api/satellites", tags=["satellites"])


@router.get("/categories", response_model=List[SatelliteCategory])
def list_categories():
    return [
        SatelliteCategory(id=cat_id, name=name)
        for cat_id, name in SATELLITE_CATEGORIES.items()
    ]


@router.get("/above/{category_id}")
async def satellites_above(category_id: int):
    try:
        return await get_satellites_overhead(category_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=429, detail=str(e))


@router.get("/position/{norad_id}", response_model=Optional[SatellitePosition])
async def satellite_position(norad_id: int):
    try:
        return await get_satellite_position_now(norad_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/passes/{norad_id}", response_model=List[SatellitePass])
async def satellite_passes(
    norad_id: int,
    days: int = Query(default=1, ge=1, le=10),
    min_el: int = Query(default=10, ge=0, le=90),
):
    try:
        return await get_satellite_passes(norad_id, days, min_el)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/track/{norad_id}", response_model=List[GroundTrackPoint])
async def ground_track(norad_id: int, minutes: float = Query(default=95.0)):
    try:
        return await get_satellite_ground_track(norad_id, minutes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/footprint/{norad_id}")
async def satellite_footprint(norad_id: int):
    """Return visibility footprint polygon (list of lat/lng) for a satellite's current position."""
    try:
        pos = await get_satellite_position_now(norad_id)
        if not pos:
            raise HTTPException(status_code=404, detail="Satellite position not found")
        return get_satellite_footprint(pos.alt_km, pos.lat, pos.lng)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/feasibility")
def tracking_feasibility(
    target: str,
    peak_rate: float = Query(description="Peak angular rate in arcsec/s"),
):
    return check_tracking_feasibility(target, peak_rate)


@router.get("/catalog")
def satellite_catalog(
    q: str = Query(default=""),
    obj_type: Optional[str] = Query(default=None, description="PAYLOAD | R/B | DEB"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0),
):
    """Search the full Celestrak satellite catalog (~33k active objects)."""
    return search_satellites(q, limit=limit, offset=offset, obj_type=obj_type)
