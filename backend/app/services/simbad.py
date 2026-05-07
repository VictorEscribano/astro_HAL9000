"""Simbad CDS resolver for DSOs and stars not in local catalog."""
import httpx
from typing import Optional

SIMBAD_TAP = "https://simbad.cds.unistra.fr/simbad/sim-tap/sync"


def resolve_simbad_sync(name: str) -> Optional[dict]:
    """Resolve object name to RA/Dec via Simbad TAP service (synchronous)."""
    query = f"""
    SELECT ra, dec, main_id, otype, flux
    FROM basic JOIN flux ON oid = oidref
    WHERE main_id = '{name.upper()}'
    AND filter = 'V'
    LIMIT 1
    """
    # Try simpler script interface first
    try:
        url = "https://simbad.cds.unistra.fr/simbad/sim-script"
        params = {
            "submit": "submit+script",
            "script": f"format object \"%COO(d;A;D) %FLUXLIST(V;F)\"\nquery id {name}"
        }
        resp = httpx.get(url, params=params, timeout=8.0)
        text = resp.text
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith(("::","!","~")):
                continue
            parts = line.split()
            if len(parts) >= 2:
                try:
                    ra_deg = float(parts[0])
                    dec_deg = float(parts[1])
                    mag = float(parts[2]) if len(parts) > 2 else None
                    return {
                        "id": name,
                        "ra_h": ra_deg / 15.0,
                        "dec_deg": dec_deg,
                        "magnitude": mag,
                        "size_arcmin": None,
                        "names": [name],
                        "common_name": "",
                    }
                except (ValueError, IndexError):
                    continue
    except Exception:
        pass
    return None
