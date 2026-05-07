"""Skyfield-based ephemeris tools: positions, sky objects, Moon info."""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from functools import lru_cache
from pathlib import Path

from skyfield.api import load, wgs84, Star
from skyfield import almanac
from skyfield.units import Angle
import numpy as np

from app.config import get_settings, EPHEMERIS_CACHE
from app.services.catalog import search_catalog, get_bright_objects, load_catalog
from app.services.hyg_catalog import get_display_stars, get_named_stars
from app.models.sky import SkyObject, MoonInfo, ObjectPosition

# ---------- loader (cached) ----------

@lru_cache(maxsize=1)
def _get_loader():
    return load.timescale()


@lru_cache(maxsize=1)
def _get_eph():
    """Load DE421 ephemeris, downloading once if needed."""
    loader = load
    # Set download dir
    from skyfield.api import Loader
    dl = Loader(str(EPHEMERIS_CACHE))
    return dl("de421.bsp")


def _ts():
    return _get_loader()


def _eph():
    return _get_eph()


def _observer(lat: float = None, lng: float = None, alt_m: float = None):
    s = get_settings()
    lat = lat or s.observer_lat
    lng = lng or s.observer_lng
    alt_m = alt_m or s.observer_alt_m
    return wgs84.latlon(lat, lng, elevation_m=alt_m)


SOLAR_SYSTEM = {
    # English
    "mercury": "mercury",
    "venus": "venus",
    "mars": "mars",
    "jupiter": "jupiter barycenter",
    "saturn": "saturn barycenter",
    "uranus": "uranus barycenter",
    "neptune": "neptune barycenter",
    "moon": "moon",
    "sun": "sun",
    # Spanish aliases — HAL receives Spanish input from the user.
    "mercurio": "mercury",
    "marte":    "mars",
    "júpiter":  "jupiter barycenter",
    "jupiter":  "jupiter barycenter",
    "saturno":  "saturn barycenter",
    "urano":    "uranus barycenter",
    "neptuno":  "neptune barycenter",
    "luna":     "moon",
    "sol":      "sun",
}

PLANET_NAMES = ["Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune"]


def _now_ts():
    return _ts().now()


def _utc_ts(dt: datetime):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return _ts().from_datetime(dt)


# ---------- object resolution ----------

def resolve_object_name(name: str):
    """Return (kind, body_key_or_catalog_entry) for any object name."""
    lower = name.strip().lower()
    if lower in SOLAR_SYSTEM:
        return ("solar", lower)
    for planet in PLANET_NAMES:
        if planet.lower() == lower:
            return ("solar", lower)
    entry = search_catalog(name)
    if entry:
        return ("catalog", entry)
    # Try Simbad as last resort (sync call for now)
    from app.services.simbad import resolve_simbad_sync
    result = resolve_simbad_sync(name)
    if result:
        return ("simbad", result)
    return (None, None)


# ---------- position calculation ----------

def get_object_position_now(name: str, lat: float = None, lng: float = None, alt_m: float = None) -> Optional[ObjectPosition]:
    ts = _ts()
    eph = _eph()
    observer = _observer(lat, lng, alt_m)
    t = ts.now()

    kind, body = resolve_object_name(name)

    if kind == "solar":
        planet_key = SOLAR_SYSTEM.get(body.lower())
        if not planet_key:
            return None
        target = eph[planet_key]
        earth = eph["earth"]
        astrometric = (earth + observer).at(t).observe(target).apparent()
        alt, az, distance = astrometric.altaz()
        ra, dec, _ = astrometric.radec()
        alt_v = alt.degrees
        az_v = az.degrees
        ra_h = ra.hours
        dec_d = dec.degrees
        dist_au = distance.au if hasattr(distance, 'au') else None
        rise, transit, set_ = _rise_transit_set_solar(name, observer, t)
        transit_alt = _transit_altitude(dec_d, lat or get_settings().observer_lat)
        return ObjectPosition(
            name=name.title(),
            ra_h=ra_h, dec_deg=dec_d,
            alt_deg=alt_v, az_deg=az_v,
            above_horizon=alt_v > 0,
            rise_utc=rise, transit_utc=transit, set_utc=set_,
            transit_alt=transit_alt,
            distance_au=dist_au,
        )

    if kind in ("catalog", "simbad"):
        entry = body
        ra_h = entry["ra_h"]
        dec_d = entry["dec_deg"]
        star = Star(ra_hours=ra_h, dec_degrees=dec_d)
        earth = eph["earth"]
        astrometric = (earth + observer).at(t).observe(star).apparent()
        alt, az, _ = astrometric.altaz()
        rise, transit, set_ = _rise_transit_set_star(ra_h, dec_d, observer, t)
        transit_alt = _transit_altitude(dec_d, lat or get_settings().observer_lat)
        return ObjectPosition(
            name=name,
            ra_h=ra_h, dec_deg=dec_d,
            alt_deg=alt.degrees, az_deg=az.degrees,
            above_horizon=alt.degrees > 0,
            rise_utc=rise, transit_utc=transit, set_utc=set_,
            transit_alt=transit_alt,
            angular_size_arcmin=entry.get("size_arcmin"),
        )
    return None


def _transit_altitude(dec_deg: float, lat_deg: float) -> float:
    """Upper transit altitude (degrees)."""
    alt = 90 - abs(lat_deg - dec_deg)
    return min(alt, 90.0)


def _rise_transit_set_star(ra_h: float, dec_d: float, observer, t_now):
    ts = _ts()
    eph = _eph()
    star = Star(ra_hours=ra_h, dec_degrees=dec_d)
    earth = eph["earth"]
    # scan next 24 hours at 1-minute resolution
    t0 = t_now
    t1 = ts.tt_jd(t0.tt + 1.0)
    times = ts.linspace(t0, t1, 1441)

    def alt_fn(t):
        return (earth + observer).at(t).observe(star).apparent().altaz()[0].degrees

    alts = np.array([alt_fn(ti) for ti in times])
    rise = transit = set_ = None
    for i in range(len(alts) - 1):
        if alts[i] < 0 and alts[i+1] >= 0:
            rise = times[i].utc_datetime()
        if alts[i] >= 0 and alts[i+1] < 0:
            set_ = times[i].utc_datetime()
    # transit = max altitude time
    if np.any(alts > 0):
        peak_idx = np.argmax(alts)
        transit = times[peak_idx].utc_datetime()
    return rise, transit, set_


def _rise_transit_set_solar(name: str, observer, t_now):
    ts = _ts()
    eph = _eph()
    planet_key = SOLAR_SYSTEM.get(name.lower())
    if not planet_key:
        return None, None, None
    try:
        target = eph[planet_key]
        earth = eph["earth"]
        t0 = t_now
        t1 = ts.tt_jd(t0.tt + 1.0)
        times = ts.linspace(t0, t1, 1441)

        def alt_fn(t):
            return (earth + observer).at(t).observe(target).apparent().altaz()[0].degrees

        alts = np.array([alt_fn(ti) for ti in times])
        rise = transit = set_ = None
        for i in range(len(alts) - 1):
            if alts[i] < 0 and alts[i+1] >= 0:
                rise = times[i].utc_datetime()
            if alts[i] >= 0 and alts[i+1] < 0:
                set_ = times[i].utc_datetime()
        if np.any(alts > 0):
            peak_idx = np.argmax(alts)
            transit = times[peak_idx].utc_datetime()
        return rise, transit, set_
    except Exception:
        return None, None, None


# ---------- sky objects tonight ----------

def get_sky_objects_tonight(lat: float = None, lng: float = None, alt_m: float = None,
                             min_alt_deg: float = 10.0) -> List[SkyObject]:
    """Vectorized sky objects: all planets + all DSOs + named stars above horizon."""
    s = get_settings()
    lat = lat or s.observer_lat
    lng = lng or s.observer_lng
    alt_m = alt_m or s.observer_alt_m
    ts = _ts()
    eph = _eph()
    observer = _observer(lat, lng, alt_m)
    earth = eph["earth"]
    t = ts.now()

    results: List[SkyObject] = []

    # ── Planets ──────────────────────────────────────────────────────────
    for planet_name in PLANET_NAMES:
        key = SOLAR_SYSTEM[planet_name.lower()]
        try:
            target = eph[key]
            astrometric = (earth + observer).at(t).observe(target).apparent()
            alt, az, _ = astrometric.altaz()
            ra, dec, _ = astrometric.radec()
            if alt.degrees >= min_alt_deg:
                results.append(SkyObject(
                    name=planet_name,
                    catalog_id=planet_name.upper(),
                    object_type="Planet",
                    ra_h=ra.hours, dec_deg=dec.degrees,
                    alt_deg=round(alt.degrees, 1),
                    az_deg=round(az.degrees, 1),
                    note=_planet_note(planet_name, alt.degrees),
                ))
        except Exception:
            pass

    # ── DSOs: vectorized batch over all catalog objects ──────────────────
    all_dsos = [o for o in get_bright_objects() if o["magnitude"] is not None]
    if all_dsos:
        try:
            ra_arr  = np.array([o["ra_h"]    for o in all_dsos])
            dec_arr = np.array([o["dec_deg"] for o in all_dsos])
            batch = Star(ra_hours=ra_arr, dec_degrees=dec_arr)
            astr  = (earth + observer).at(t).observe(batch).apparent()
            alts_deg, azs_deg, _ = astr.altaz()
            alt_vals = alts_deg.degrees
            az_vals  = azs_deg.degrees
            for i, obj in enumerate(all_dsos):
                a = float(alt_vals[i]) if hasattr(alt_vals, '__len__') else float(alt_vals)
                z = float(az_vals[i])  if hasattr(az_vals,  '__len__') else float(az_vals)
                if a < min_alt_deg:
                    continue
                display_name = obj["names"][0] if obj["names"] else obj["id"]
                if obj.get("common_name"):
                    display_name = f"{display_name} ({obj['common_name']})"
                results.append(SkyObject(
                    name=display_name,
                    catalog_id=obj["id"],
                    object_type=obj.get("type", "DSO"),
                    ra_h=obj["ra_h"], dec_deg=obj["dec_deg"],
                    alt_deg=round(a, 1), az_deg=round(z, 1),
                    magnitude=obj["magnitude"],
                    angular_size_arcmin=obj.get("size_arcmin"),
                    note=_dso_note(obj),
                ))
        except Exception:
            pass

    # ── Named stars: vectorized batch ────────────────────────────────────
    named = get_named_stars()
    if named:
        try:
            ra_arr  = np.array([s["ra_h"]    for s in named])
            dec_arr = np.array([s["dec_deg"] for s in named])
            batch = Star(ra_hours=ra_arr, dec_degrees=dec_arr)
            astr  = (earth + observer).at(t).observe(batch).apparent()
            alts_deg, azs_deg, _ = astr.altaz()
            alt_vals = alts_deg.degrees
            az_vals  = azs_deg.degrees
            for i, star in enumerate(named):
                a = float(alt_vals[i]) if hasattr(alt_vals, '__len__') else float(alt_vals)
                z = float(az_vals[i])  if hasattr(az_vals,  '__len__') else float(az_vals)
                if a < min_alt_deg:
                    continue
                results.append(SkyObject(
                    name=star["proper"],
                    catalog_id=star["id"],
                    object_type="Star",
                    ra_h=star["ra_h"], dec_deg=star["dec_deg"],
                    alt_deg=round(a, 1), az_deg=round(z, 1),
                    magnitude=star["magnitude"],
                    note=f"{star.get('spectral','?')}-type star, {star.get('constellation','')}",
                ))
        except Exception:
            pass

    results.sort(key=lambda x: (x.object_type != "Planet", -(x.alt_deg or 0)))
    return results


def get_stars_tonight(lat: float = None, lng: float = None, alt_m: float = None,
                      max_mag: float = 5.5) -> List[dict]:
    """Return all stars above horizon up to max_mag — for sky chart rendering."""
    s = get_settings()
    lat = lat or s.observer_lat
    lng = lng or s.observer_lng
    alt_m = alt_m or s.observer_alt_m
    ts = _ts()
    eph = _eph()
    observer = _observer(lat, lng, alt_m)
    earth = eph["earth"]
    t = ts.now()

    display_stars = [s for s in get_display_stars() if s["magnitude"] <= max_mag]
    if not display_stars:
        return []

    ra_arr  = np.array([s["ra_h"]    for s in display_stars])
    dec_arr = np.array([s["dec_deg"] for s in display_stars])
    try:
        batch = Star(ra_hours=ra_arr, dec_degrees=dec_arr)
        astr  = (earth + observer).at(t).observe(batch).apparent()
        alts_deg, azs_deg, _ = astr.altaz()
        alt_vals = alts_deg.degrees
        az_vals  = azs_deg.degrees
    except Exception:
        return []

    out = []
    for i, star in enumerate(display_stars):
        a = float(alt_vals[i]) if hasattr(alt_vals, '__len__') else float(alt_vals)
        z = float(az_vals[i])  if hasattr(az_vals,  '__len__') else float(az_vals)
        if a < -5:
            continue
        out.append({
            "name": star["proper"] or star["name"],
            "alt_deg": round(a, 2),
            "az_deg": round(z, 2),
            "magnitude": star["magnitude"],
            "spectral": star["spectral"],
            "color": star["color"],
        })
    return out


def _planet_note(name: str, alt: float) -> str:
    if alt > 60:
        return f"Excellent position ({alt:.0f}° altitude). Good for imaging."
    elif alt > 30:
        return f"Good position ({alt:.0f}° altitude)."
    return f"Low altitude ({alt:.0f}°). Atmospheric dispersion may affect image quality."


def _dso_note(obj: dict) -> str:
    t = obj.get("type", "")
    size = obj.get("size_arcmin")
    mag = obj.get("magnitude")
    parts = []
    if size:
        if size > 30:
            parts.append(f"Large ({size:.0f}' across) — suits wide field")
        elif size > 5:
            parts.append(f"{size:.1f}' — suits medium focal length")
        else:
            parts.append(f"Small ({size:.1f}') — needs long focal length")
    if mag:
        if mag < 6:
            parts.append("visible naked eye")
        elif mag < 9:
            parts.append("easy binoculars")
        else:
            parts.append(f"mag {mag:.1f}")
    return ". ".join(parts) if parts else ""


# ---------- Moon info ----------

def get_moon_info_now(lat: float = None, lng: float = None, alt_m: float = None,
                      target_ra_h: float = None) -> MoonInfo:
    s = get_settings()
    lat = lat or s.observer_lat
    lng = lng or s.observer_lng
    alt_m = alt_m or s.observer_alt_m
    ts = _ts()
    eph = _eph()
    observer = _observer(lat, lng, alt_m)
    earth = eph["earth"]
    t = ts.now()

    moon = eph["moon"]
    sun = eph["sun"]

    # Phase: angle sun-earth-moon
    sun_astrometric = earth.at(t).observe(sun)
    moon_astrometric = earth.at(t).observe(moon)
    sun_ra, sun_dec, _ = sun_astrometric.apparent().radec()
    moon_ra, moon_dec, _ = moon_astrometric.apparent().radec()

    # Elongation in degrees → phase 0-1
    from skyfield import almanac as alm
    phase_angle = alm.moon_phase(eph, t)
    phase_0_1 = phase_angle.degrees / 360.0
    illumination = (1 - np.cos(np.radians(phase_angle.degrees))) / 2 * 100

    phase_name = _phase_name(phase_0_1)

    # Position
    astrometric = (earth + observer).at(t).observe(moon).apparent()
    alt, az, dist = astrometric.altaz()
    ang_diam = 2 * np.degrees(np.arctan(1737.4 / (dist.km))) * 60  # arcmin

    rise, transit, set_ = _rise_transit_set_solar("moon", observer, t)

    # Interference: illumination > 30% and up during the night
    interference = illumination > 30 and alt.degrees > 0
    interference_note = ""
    if interference:
        if illumination > 80:
            interference_note = f"Bright Moon ({illumination:.0f}% illuminated) will severely impact faint objects."
        else:
            interference_note = f"Moon ({illumination:.0f}% illuminated) will reduce contrast for faint nebulae."

    return MoonInfo(
        phase=phase_0_1,
        illumination_pct=round(illumination, 1),
        phase_name=phase_name,
        alt_deg=round(alt.degrees, 1),
        az_deg=round(az.degrees, 1),
        rise_utc=rise, set_utc=set_, transit_utc=transit,
        angular_diameter_arcmin=round(ang_diam, 2),
        interference=interference,
        interference_note=interference_note,
    )


def _phase_name(phase: float) -> str:
    if phase < 0.04 or phase > 0.96:
        return "New Moon"
    elif phase < 0.24:
        return "Waxing Crescent"
    elif phase < 0.26:
        return "First Quarter"
    elif phase < 0.49:
        return "Waxing Gibbous"
    elif phase < 0.51:
        return "Full Moon"
    elif phase < 0.74:
        return "Waning Gibbous"
    elif phase < 0.76:
        return "Last Quarter"
    else:
        return "Waning Crescent"


# ---------- sky track (for frontend) ----------

def get_object_track(name: str, hours: float = 4.0, lat: float = None,
                     lng: float = None, alt_m: float = None) -> list:
    """Return list of {time, alt, az} for the next N hours."""
    ts = _ts()
    eph = _eph()
    observer = _observer(lat, lng, alt_m)
    earth = eph["earth"]
    t_now = ts.now()
    n_points = int(hours * 12)  # every 5 minutes
    times = ts.linspace(t_now, ts.tt_jd(t_now.tt + hours / 24), n_points)

    kind, body = resolve_object_name(name)
    track = []
    for t in times:
        if kind == "solar":
            key = SOLAR_SYSTEM.get(body.lower())
            astr = (earth + observer).at(t).observe(eph[key]).apparent()
        elif kind in ("catalog", "simbad"):
            star = Star(ra_hours=body["ra_h"], dec_degrees=body["dec_deg"])
            astr = (earth + observer).at(t).observe(star).apparent()
        else:
            break
        alt, az, _ = astr.altaz()
        track.append({
            "time": t.utc_datetime().isoformat(),
            "alt": round(alt.degrees, 2),
            "az": round(az.degrees, 2),
        })
    return track
