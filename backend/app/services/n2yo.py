"""N2YO API client with rate limiting and TLE caching."""
import httpx
import asyncio
from typing import Optional
from datetime import datetime

from app.config import get_settings
from app.services.cache import check_rate_limit, get_tle, put_tle

N2YO_BASE = "https://api.n2yo.com/rest/v1/satellite"

SATELLITE_CATEGORIES = {
    2:  "International Space Station",
    54: "Chinese Space Station (Tiangong)",
    1:  "Brightest 100",
    52: "Starlink",
    20: "GPS Operational",
    21: "Glonass Operational",
    22: "Galileo",
    35: "Beidou",
    30: "Military",
    15: "Iridium",
    17: "Globalstar",
    10: "Geostationary",
    26: "Space & Earth Science",
    3:  "Weather",
    18: "Amateur Radio",
    6:  "Disaster Monitoring",
    8:  "Earth Resources",
    28: "CubeSats",
    32: "Engineering",
    24: "Experimental",
}


async def _get(path: str, cost: int = 1) -> Optional[dict]:
    settings = get_settings()
    if not settings.n2yo_api_key:
        raise ValueError("N2YO_API_KEY not configured")
    if not await check_rate_limit(cost):
        raise RuntimeError("N2YO rate limit reached (990/hr)")
    url = f"{N2YO_BASE}{path}&apiKey={settings.n2yo_api_key}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


async def fetch_tle(norad_id: int) -> dict:
    """Fetch TLE for a satellite, using cache when fresh (<1 hr)."""
    cached = await get_tle(norad_id, max_age_s=3600)
    if cached:
        return cached
    data = await _get(f"/tle/{norad_id}?")
    tle_data = data.get("tle", "")
    lines = [l.strip() for l in tle_data.strip().split("\n") if l.strip()]
    if len(lines) < 2:
        raise ValueError(f"Invalid TLE data for NORAD {norad_id}: {tle_data!r}")
    name = data.get("info", {}).get("satname", f"NORAD-{norad_id}")
    line1, line2 = lines[-2], lines[-1]
    await put_tle(norad_id, name, line1, line2)
    return {"name": name, "line1": line1, "line2": line2, "fetched_at": None}


async def get_satellites_above(lat: float, lng: float, alt_m: float, category_id: int) -> dict:
    """Return satellites of given category currently above the observer."""
    alt_km = alt_m / 1000.0
    data = await _get(f"/above/{lat}/{lng}/{alt_km}/90/{category_id}?")
    return data


async def get_visual_passes(norad_id: int, lat: float, lng: float, alt_m: float,
                             days: int = 1, min_el: int = 10) -> dict:
    alt_km = alt_m / 1000.0
    data = await _get(f"/visualpasses/{norad_id}/{lat}/{lng}/{alt_km}/{days}/{min_el}?")
    return data


async def get_positions(norad_id: int, lat: float, lng: float, alt_m: float, seconds: int = 1) -> dict:
    """Use sparingly — prefer sgp4 local propagation for ground tracks."""
    alt_km = alt_m / 1000.0
    data = await _get(f"/positions/{norad_id}/{lat}/{lng}/{alt_km}/{seconds}?")
    return data
