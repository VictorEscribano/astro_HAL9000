"""Celestrak satellite catalog (satcat.csv) — ~33k active, 68k total."""
import csv
from pathlib import Path
from functools import lru_cache
from typing import List, Optional

SATCAT_CSV = Path(__file__).parent.parent.parent / "data" / "satcat.csv"

# Status codes that mean the satellite is still in orbit (not decayed)
IN_ORBIT = {"+", "-", "P", "B", "S", "p", ""}


@lru_cache(maxsize=1)
def load_satcat() -> List[dict]:
    """Load all non-decayed satellites."""
    sats: List[dict] = []
    with open(SATCAT_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("OPS_STATUS_CODE", "D") == "D":
                continue
            norad_str = row.get("NORAD_CAT_ID", "")
            try:
                norad = int(norad_str)
            except ValueError:
                continue
            name = row.get("OBJECT_NAME", "").strip()
            if not name:
                continue
            try:
                period = float(row["PERIOD"]) if row.get("PERIOD") else None
            except ValueError:
                period = None
            try:
                incl = float(row["INCLINATION"]) if row.get("INCLINATION") else None
            except ValueError:
                incl = None
            try:
                apogee = int(float(row["APOGEE"])) if row.get("APOGEE") else None
            except ValueError:
                apogee = None

            sats.append({
                "norad_id": norad,
                "name": name,
                "obj_type": row.get("OBJECT_TYPE", "").strip(),
                "owner": row.get("OWNER", "").strip(),
                "launch_date": row.get("LAUNCH_DATE", "").strip(),
                "status": row.get("OPS_STATUS_CODE", "").strip(),
                "period_min": period,
                "inclination": incl,
                "apogee_km": apogee,
            })
    return sats


def search_satellites(query: str, limit: int = 50, offset: int = 0,
                      obj_type: Optional[str] = None) -> dict:
    """Search satellite catalog. obj_type: 'PAY'|'PAYLOAD'|'R/B'|'DEB', etc."""
    q = query.strip().upper()
    all_sats = load_satcat()

    # Accept "PAYLOAD" as alias for "PAY" (the CSV stores 3-letter codes)
    _type = {"PAYLOAD": "PAY", "ROCKET": "R/B", "DEBRIS": "DEB"}.get(obj_type or "", obj_type)

    if q or _type:
        matches = [
            s for s in all_sats
            if (not _type or s["obj_type"] == _type)
            and (not q or q in s["name"] or q in str(s["norad_id"]))
        ]
    else:
        # Default: return only payloads
        matches = [s for s in all_sats if s["obj_type"] == "PAY"]

    total = len(matches)
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "results": matches[offset: offset + limit],
    }


def get_satellite_name(norad_id: int) -> Optional[str]:
    for s in load_satcat():
        if s["norad_id"] == norad_id:
            return s["name"]
    return None
