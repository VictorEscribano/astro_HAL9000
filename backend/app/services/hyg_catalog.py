"""HYG star catalog v42 — 119,627 entries, ~499 named, ~8,835 naked-eye."""
import csv
from pathlib import Path
from functools import lru_cache
from typing import List, Optional

HYG_CSV = Path(__file__).parent.parent.parent / "data" / "hyg_full.csv"

# Spectral class → hex color for rendering
SPECTRAL_COLOR: dict[str, str] = {
    "O": "#9bb0ff",
    "B": "#aabfff",
    "A": "#cad7ff",
    "F": "#f8f7ff",
    "G": "#fff4ea",
    "K": "#ffd2a1",
    "M": "#ffcc6f",
}


@lru_cache(maxsize=1)
def load_hyg(max_mag: float = 8.0) -> List[dict]:
    """Load HYG stars up to max_mag. Returns list of dicts."""
    stars: List[dict] = []
    with open(HYG_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                mag = float(row["mag"])
            except (ValueError, KeyError):
                continue
            if mag > max_mag:
                continue
            proper = row.get("proper", "").strip()
            bf = row.get("bf", "").strip()
            hd = row.get("hd", "").strip()
            try:
                ra_h = float(row["ra"])
                dec_deg = float(row["dec"])
            except (ValueError, KeyError):
                continue

            spect = (row.get("spect") or "")[:1].upper()
            con = row.get("con", "").strip()

            # Build display name: prefer proper name, then Bayer, then HD number
            if proper:
                display = proper
            elif bf:
                display = bf
            elif hd:
                display = f"HD {hd}"
            else:
                continue  # no name at all — skip for catalog

            stars.append({
                "id": f"HIP{row.get('hip','')}" if row.get("hip") else f"HD{hd}",
                "name": display,
                "proper": proper,
                "ra_h": ra_h,
                "dec_deg": dec_deg,
                "magnitude": round(mag, 2),
                "spectral": spect,
                "constellation": con,
                "color": SPECTRAL_COLOR.get(spect, "#ffffff"),
                "type": "Star",
            })
    return stars


@lru_cache(maxsize=1)
def get_named_stars() -> List[dict]:
    """Return only the ~499 stars with proper (common) names."""
    return [s for s in load_hyg() if s["proper"]]


@lru_cache(maxsize=1)
def get_display_stars(max_mag: float = 6.5) -> List[dict]:
    """Return stars suitable for sky chart display (naked eye + a bit more)."""
    return [s for s in load_hyg() if s["magnitude"] <= max_mag]


def search_stars(query: str, limit: int = 100, offset: int = 0) -> List[dict]:
    q = query.strip().lower()
    results = []
    for s in load_hyg():
        name_lower = s["name"].lower()
        proper_lower = s["proper"].lower() if s["proper"] else ""
        if q in name_lower or (proper_lower and q in proper_lower) or q in s["constellation"].lower():
            results.append(s)
    return results[offset:offset + limit]
