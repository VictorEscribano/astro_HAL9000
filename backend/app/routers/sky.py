"""Sky / ephemeris endpoints."""
from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List

from app.tools.ephemeris import (
    get_sky_objects_tonight, get_object_position_now,
    get_moon_info_now, get_object_track, get_stars_tonight,
)
from app.models.sky import SkyObject, MoonInfo, ObjectPosition
from app.services.catalog import load_catalog, search_catalog
from app.services.hyg_catalog import search_stars, get_named_stars
from app.config import get_settings

router = APIRouter(prefix="/api/sky", tags=["sky"])


@router.get("/objects-tonight", response_model=List[SkyObject])
def objects_tonight(
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    alt_m: Optional[float] = None,
    min_alt: float = Query(default=10.0),
):
    return get_sky_objects_tonight(lat, lng, alt_m, min_alt)


@router.get("/stars-tonight")
def stars_tonight(
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    alt_m: Optional[float] = None,
    max_mag: float = Query(default=5.5),
):
    """All stars above horizon for sky chart rendering."""
    return get_stars_tonight(lat, lng, alt_m, max_mag)


@router.get("/catalog")
def catalog_search(
    q: str = Query(default=""),
    type: str = Query(default="all"),   # all | dso | star | planet
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0),
):
    """Search entire celestial catalog: DSOs (NGC/IC/Messier), named stars, planets."""
    results = []
    type_lc = type.lower()

    # DSOs
    if type_lc in ("all", "dso"):
        q_upper = q.strip().upper()
        for obj in load_catalog():
            if q_upper:
                names_upper = [n.upper() for n in obj["names"]]
                common = obj.get("common_name", "").upper()
                if q_upper not in " ".join(names_upper + [obj["id"].upper(), common]):
                    continue
            display_name = obj["names"][0] if obj["names"] else obj["id"]
            if obj.get("common_name"):
                display_name = f"{display_name} ({obj['common_name']})"
            results.append({
                "id": obj["id"],
                "name": display_name,
                "catalog_id": obj["id"],
                "object_type": obj.get("type", "DSO"),
                "ra_h": obj["ra_h"],
                "dec_deg": obj["dec_deg"],
                "magnitude": obj.get("magnitude"),
                "angular_size_arcmin": obj.get("size_arcmin"),
            })

    # Stars (named only if no query, or search all with query)
    if type_lc in ("all", "star"):
        stars = search_stars(q, limit=500) if q else get_named_stars()
        for s in stars:
            results.append({
                "id": s["id"],
                "name": s["proper"] or s["name"],
                "catalog_id": s["id"],
                "object_type": "Star",
                "ra_h": s["ra_h"],
                "dec_deg": s["dec_deg"],
                "magnitude": s["magnitude"],
                "spectral": s.get("spectral"),
                "constellation": s.get("constellation"),
            })

    # Planets (always include when searching all or planet)
    if type_lc in ("all", "planet") and (not q or any(
        q.strip().lower() in p.lower() for p in
        ["mercury","venus","mars","jupiter","saturn","uranus","neptune","moon","sun"]
    )):
        for p in ["Sun","Moon","Mercury","Venus","Mars","Jupiter","Saturn","Uranus","Neptune"]:
            if not q or q.strip().lower() in p.lower():
                results.append({
                    "id": p.upper(),
                    "name": p,
                    "catalog_id": p.upper(),
                    "object_type": "Planet",
                    "ra_h": None,
                    "dec_deg": None,
                    "magnitude": None,
                })

    total = len(results)
    page = results[offset: offset + limit]
    return {"total": total, "offset": offset, "limit": limit, "results": page}


@router.get("/object/{name}", response_model=ObjectPosition)
def object_position(
    name: str,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    alt_m: Optional[float] = None,
):
    pos = get_object_position_now(name, lat, lng, alt_m)
    if not pos:
        raise HTTPException(status_code=404, detail=f"Object '{name}' not found")
    return pos


@router.get("/moon", response_model=MoonInfo)
def moon_info(lat: Optional[float] = None, lng: Optional[float] = None, alt_m: Optional[float] = None):
    return get_moon_info_now(lat, lng, alt_m)


@router.get("/track/{name}")
def object_track(
    name: str,
    hours: float = Query(default=4.0),
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    alt_m: Optional[float] = None,
):
    return get_object_track(name, hours, lat, lng, alt_m)


@router.get("/observer")
def observer_config():
    s = get_settings()
    return {
        "lat": s.observer_lat,
        "lng": s.observer_lng,
        "alt_m": s.observer_alt_m,
        "name": s.observer_name,
    }
