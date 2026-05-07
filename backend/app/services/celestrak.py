"""Celestrak TLE catalog — search satellites by name (no API key needed)."""
import httpx
import re
from typing import Optional
from functools import lru_cache
import time

# Celestrak GP catalog — name search (JSON and TLE formats)
CELESTRAK_GP_JSON = "https://celestrak.org/SOCRATES/query.php"  # GP JSON endpoint
CELESTRAK_GP_TLE  = "https://celestrak.org/SOCRATES/query.php"  # GP TLE endpoint

_SATCAT_CACHE: Optional[list] = None
_SATCAT_LOADED_AT: float = 0


async def search_satellite_by_name(query: str) -> list[dict]:
    """Search Celestrak satellite catalog by name. Returns list of matches with NORAD ID."""
    import httpx

    # Use Celestrak GP catalog name search (JSON format)
    url = f"https://celestrak.org/SOCRATES/query.php?NAME={query}&FORMAT=json"

    # Try GP catalog search
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://celestrak.org/SOCRATES/query.php",
                params={"NAME": query, "FORMAT": "json"},
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    results = []
                    for sat in data[:10]:
                        norad = sat.get("NORAD_CAT_ID") or sat.get("OBJECT_ID", "")
                        name = sat.get("OBJECT_NAME", "")
                        if norad:
                            results.append({"norad_id": int(norad), "name": name})
                    return results
    except Exception:
        pass

    # Fallback: Celestrak TLE text search
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://celestrak.org/SOCRATES/query.php",
                params={"NAME": query, "FORMAT": "TLE"},
            )
            if resp.status_code == 200 and resp.text.strip():
                return _parse_tle_text(resp.text)
    except Exception:
        pass

    return []


def _parse_tle_text(text: str) -> list[dict]:
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    results = []
    i = 0
    while i < len(lines) - 2:
        name_line = lines[i]
        line1 = lines[i + 1]
        line2 = lines[i + 2]
        if line1.startswith("1 ") and line2.startswith("2 "):
            try:
                norad = int(line1[2:7].strip())
                results.append({"norad_id": norad, "name": name_line})
            except ValueError:
                pass
            i += 3
        else:
            i += 1
    return results


# Well-known satellite name → NORAD ID mappings for common queries
KNOWN_SATELLITES: dict[str, int] = {
    "iss": 25544,
    "international space station": 25544,
    "estacion espacial internacional": 25544,
    "tiangong": 48274,
    "css": 48274,
    "hubble": 20580,
    "hubble space telescope": 20580,
    "hst": 20580,
    "james webb": 50463,
    "jwst": 50463,
    "mohammed vi-a": 42792,
    "mohammed vi a": 42792,
    "mohammed 6a": 42792,
    "mohammed vi-b": 43596,
    "mohammed vi b": 43596,
    "mohammed 6b": 43596,
    "mohammed v": 42792,   # user likely means Mohammed VI-A
    "mohammed vi": 42792,
}


def resolve_known_satellite(name: str) -> Optional[int]:
    """Resolve common satellite names to NORAD IDs instantly."""
    return KNOWN_SATELLITES.get(name.strip().lower())
