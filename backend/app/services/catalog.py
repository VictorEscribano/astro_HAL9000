"""Offline NGC/IC/Messier catalog loader from OpenNGC CSV."""
import csv
from pathlib import Path
from typing import Optional, List
from functools import lru_cache

NGC_CSV = Path(__file__).parent.parent.parent / "data" / "ngc_catalog.csv"


def _parse_ra(ra_str: str) -> Optional[float]:
    """HH:MM:SS.s → decimal hours."""
    try:
        parts = ra_str.strip().split(":")
        h, m, s = float(parts[0]), float(parts[1]), float(parts[2])
        return h + m / 60 + s / 3600
    except Exception:
        return None


def _parse_dec(dec_str: str) -> Optional[float]:
    """±DD:MM:SS.s → decimal degrees."""
    try:
        sign = -1 if dec_str.startswith("-") else 1
        parts = dec_str.strip().lstrip("+-").split(":")
        d, m, s = float(parts[0]), float(parts[1]), float(parts[2])
        return sign * (d + m / 60 + s / 3600)
    except Exception:
        return None


@lru_cache(maxsize=1)
def load_catalog() -> List[dict]:
    objects = []
    with open(NGC_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            ra = _parse_ra(row.get("RA", ""))
            dec = _parse_dec(row.get("Dec", ""))
            if ra is None or dec is None:
                continue
            mag_str = row.get("V-Mag") or row.get("B-Mag") or ""
            try:
                mag = float(mag_str)
            except ValueError:
                mag = None
            size_str = row.get("MajAx", "")
            try:
                size = float(size_str)   # arcminutes
            except ValueError:
                size = None
            names = [row.get("Name", "").strip()]
            m_name = row.get("M", "").strip()
            if m_name:
                try:
                    names.append(f"M{int(m_name)}")
                except ValueError:
                    names.append(f"M{m_name}")
            objects.append({
                "id": row.get("Name", "").strip(),
                "type": row.get("Type", "").strip(),
                "ra_h": ra,
                "dec_deg": dec,
                "magnitude": mag,
                "size_arcmin": size,
                "names": [n for n in names if n],
                "common_name": row.get("Common names", "").strip(),
            })
    return objects


def _normalize_id(q: str) -> list:
    """Return list of candidate IDs from query string."""
    candidates = [q]
    # NGC/IC: add zero-padded versions
    for prefix in ("NGC", "IC"):
        if q.startswith(prefix):
            num = q[len(prefix):]
            if num.isdigit():
                candidates.append(f"{prefix}{int(num):04d}")
    return candidates


def search_catalog(query: str) -> Optional[dict]:
    """Find object by NGC/IC/Messier ID or common name (case-insensitive)."""
    q = query.strip().upper()
    catalog = load_catalog()
    # Normalize Messier format
    if q.startswith("M") and q[1:].isdigit():
        messier = f"M{q[1:]}"
        for obj in catalog:
            if messier in [n.upper() for n in obj["names"]]:
                return obj
    candidates = _normalize_id(q)
    for obj in catalog:
        for name in obj["names"]:
            if name.upper() in candidates:
                return obj
    # fuzzy: common name substring
    for obj in catalog:
        if obj["common_name"] and q in obj["common_name"].upper():
            return obj
    return None


def get_bright_objects(min_alt_deg: float = 20.0, max_mag: float = 12.0) -> List[dict]:
    return [o for o in load_catalog() if o["magnitude"] is not None and o["magnitude"] <= max_mag]
