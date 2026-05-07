"""Satellite tools: passes, overhead list, ground track, tracking feasibility."""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Optional
import numpy as np

from sgp4.api import Satrec, jday
from sgp4 import exporter

from app.config import get_settings
from app.services.n2yo import fetch_tle, get_satellites_above, get_visual_passes
from app.models.satellite import (
    SatellitePosition, SatellitePass, GroundTrackPoint, TrackingFeasibility
)


def _jday_now():
    dt = datetime.now(timezone.utc)
    return jday(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second + dt.microsecond / 1e6)


def _propagate_tle(line1: str, line2: str, dt: datetime) -> Optional[dict]:
    """Propagate TLE to given UTC datetime. Returns ECI position/velocity."""
    sat = Satrec.twoline2rv(line1, line2)
    jd, fr = jday(dt.year, dt.month, dt.day, dt.hour, dt.minute,
                   dt.second + dt.microsecond / 1e6)
    e, r, v = sat.sgp4(jd, fr)
    if e != 0:
        return None
    return {"r": r, "v": v}


def _eci_to_lla(r: list, dt: datetime) -> tuple:
    """ECI (km) → geographic lat, lon, alt (km)."""
    # GMST
    import math
    jd, fr = jday(dt.year, dt.month, dt.day, dt.hour, dt.minute,
                   dt.second + dt.microsecond / 1e6)
    t_ut1 = (jd + fr - 2451545.0) / 36525.0
    gmst = (67310.54841 + (876600 * 3600 + 8640184.812866) * t_ut1
            + 0.093104 * t_ut1**2 - 6.2e-6 * t_ut1**3) % 86400
    gmst = gmst / 240.0  # degrees
    gmst_rad = math.radians(gmst)

    x, y, z = r
    # rotate from ECI to ECEF
    lon_rad = math.atan2(y, x) - gmst_rad
    lon = math.degrees(lon_rad)
    while lon > 180: lon -= 360
    while lon < -180: lon += 360

    p = math.sqrt(x**2 + y**2)
    # WGS84 iterative
    a = 6378.137
    f = 1 / 298.257223563
    b = a * (1 - f)
    e2 = 1 - (b/a)**2
    lat = math.atan2(z, p * (1 - e2))
    for _ in range(5):
        N_val = a / math.sqrt(1 - e2 * math.sin(lat)**2)
        lat = math.atan2(z + e2 * N_val * math.sin(lat), p)
    N_val = a / math.sqrt(1 - e2 * math.sin(lat)**2)
    alt = p / math.cos(lat) - N_val if abs(math.cos(lat)) > 1e-10 else abs(z) / math.sin(lat) - N_val * (1 - e2)
    return math.degrees(lat), lon, alt


def _altaz_from_eci(r: list, observer_lat: float, observer_lng: float, observer_alt_km: float, dt: datetime):
    """Compute altitude/azimuth of satellite from observer."""
    import math
    jd, fr = jday(dt.year, dt.month, dt.day, dt.hour, dt.minute,
                   dt.second + dt.microsecond / 1e6)
    t_ut1 = (jd + fr - 2451545.0) / 36525.0
    gmst = (67310.54841 + (876600 * 3600 + 8640184.812866) * t_ut1
            + 0.093104 * t_ut1**2 - 6.2e-6 * t_ut1**3) % 86400
    gmst_rad = math.radians(gmst / 240.0)

    lat_r = math.radians(observer_lat)
    lon_r = math.radians(observer_lng)

    # Observer ECEF position (km)
    a = 6378.137
    f = 1 / 298.257223563
    e2 = 2*f - f**2
    N_obs = a / math.sqrt(1 - e2 * math.sin(lat_r)**2)
    obs_x = (N_obs + observer_alt_km) * math.cos(lat_r) * math.cos(lon_r + gmst_rad)
    obs_y = (N_obs + observer_alt_km) * math.cos(lat_r) * math.sin(lon_r + gmst_rad)
    obs_z = (N_obs * (1 - e2) + observer_alt_km) * math.sin(lat_r)

    dx = r[0] - obs_x
    dy = r[1] - obs_y
    dz = r[2] - obs_z
    rng = math.sqrt(dx**2 + dy**2 + dz**2)

    # Rotate to SEZ (south, east, zenith) frame
    sin_lat, cos_lat = math.sin(lat_r), math.cos(lat_r)
    sin_lon, cos_lon = math.sin(lon_r + gmst_rad), math.cos(lon_r + gmst_rad)

    s = sin_lat * cos_lon * dx + sin_lat * sin_lon * dy - cos_lat * dz
    e = -sin_lon * dx + cos_lon * dy
    z = cos_lat * cos_lon * dx + cos_lat * sin_lon * dy + sin_lat * dz

    el = math.degrees(math.asin(z / rng))
    az = math.degrees(math.atan2(-s, e)) + 90
    if az < 0: az += 360
    if az >= 360: az -= 360

    return el, az, rng


async def get_satellite_ground_track(norad_id: int, minutes: float = 190.0) -> List[GroundTrackPoint]:
    """Propagate satellite for two orbital periods. Marks each point visible if above observer horizon."""
    s = get_settings()
    tle = await fetch_tle(norad_id)
    now = datetime.now(timezone.utc)
    track = []
    step_s = 30  # finer resolution to catch short visibility windows
    total_steps = int(minutes * 60 / step_s)
    for i in range(total_steps):
        dt = now + timedelta(seconds=i * step_s)
        result = _propagate_tle(tle["line1"], tle["line2"], dt)
        if result:
            lat, lon, alt = _eci_to_lla(result["r"], dt)
            el, _, _ = _altaz_from_eci(
                result["r"], s.observer_lat, s.observer_lng, s.observer_alt_m / 1000.0, dt
            )
            track.append(GroundTrackPoint(
                lat=round(lat, 4), lng=round(lon, 4),
                alt_km=round(alt, 2), timestamp=dt,
                el_deg=round(el, 2), visible=el > 0,
            ))
    return track


def get_satellite_footprint(alt_km: float, lat: float, lng: float, n_points: int = 72) -> list[dict]:
    """Compute the visibility footprint circle for a satellite at given altitude.
    Returns list of {lat, lng} polygon points.
    """
    import math
    R_earth = 6371.0
    # Angular radius of the footprint (horizon from satellite)
    rho = math.degrees(math.acos(R_earth / (R_earth + alt_km)))

    lat_r = math.radians(lat)
    lng_r = math.radians(lng)

    points = []
    for i in range(n_points + 1):
        bearing = math.radians(i * 360 / n_points)
        # Destination point on Earth's surface at angular distance rho
        d = math.radians(rho)
        fp_lat = math.asin(
            math.sin(lat_r) * math.cos(d)
            + math.cos(lat_r) * math.sin(d) * math.cos(bearing)
        )
        fp_lng = lng_r + math.atan2(
            math.sin(bearing) * math.sin(d) * math.cos(lat_r),
            math.cos(d) - math.sin(lat_r) * math.sin(fp_lat),
        )
        points.append({"lat": round(math.degrees(fp_lat), 4), "lng": round(math.degrees(fp_lng), 4)})
    return points


async def get_satellite_position_now(norad_id: int) -> Optional[SatellitePosition]:
    tle = await fetch_tle(norad_id)
    s = get_settings()
    now = datetime.now(timezone.utc)
    result = _propagate_tle(tle["line1"], tle["line2"], now)
    if not result:
        return None
    lat, lon, alt = _eci_to_lla(result["r"], now)
    el, az, _ = _altaz_from_eci(result["r"], s.observer_lat, s.observer_lng, s.observer_alt_m / 1000, now)
    # RA/Dec approximate from ECI vector
    import math
    r = result["r"]
    r_norm = math.sqrt(sum(x**2 for x in r))
    ra_deg = math.degrees(math.atan2(r[1], r[0]))
    if ra_deg < 0: ra_deg += 360
    dec_deg = math.degrees(math.asin(r[2] / r_norm))
    return SatellitePosition(
        norad_id=norad_id, name=tle["name"],
        lat=round(lat, 4), lng=round(lon, 4), alt_km=round(alt, 2),
        az_deg=round(az, 2), el_deg=round(el, 2),
        ra_deg=round(ra_deg, 3), dec_deg=round(dec_deg, 3),
        timestamp=now,
    )


async def get_satellite_passes(norad_id: int, days: int = 1, min_el: int = 10) -> List[SatellitePass]:
    s = get_settings()
    data = await get_visual_passes(norad_id, s.observer_lat, s.observer_lng, s.observer_alt_m, days, min_el)
    passes = []
    tle_data = await fetch_tle(norad_id)
    for p in data.get("passes", []):
        try:
            start = datetime.fromtimestamp(p["startUTC"], tz=timezone.utc)
            end = datetime.fromtimestamp(p["endUTC"], tz=timezone.utc)
            passes.append(SatellitePass(
                norad_id=norad_id,
                name=tle_data["name"],
                start_utc=start, end_utc=end,
                max_el_deg=p.get("maxEl", 0),
                start_az_deg=p.get("startAzDeg", 0),
                end_az_deg=p.get("endAzDeg", 0),
                duration_s=p.get("duration", 0),
                mag=p.get("mag"),
            ))
        except Exception:
            continue
    return passes


async def get_satellites_overhead(category_id: int) -> list:
    s = get_settings()
    data = await get_satellites_above(s.observer_lat, s.observer_lng, s.observer_alt_m, category_id)
    return data.get("above", [])


def check_tracking_feasibility(
    target_name: str,
    peak_rate_arcsec_s: float,
    lat: float = None,
) -> TrackingFeasibility:
    """Check if OAT can track a given angular rate."""
    s = get_settings()
    # Max tracking rate: step_rate / (steps_per_rev * microstepping * gear_ratio) * 360 * 3600 arcsec/rev
    steps_per_arcsec = (s.oat_steps_per_rev * s.oat_microstepping * s.oat_ra_gear_ratio) / (360.0 * 3600.0)
    max_rate = s.oat_max_step_rate_hz / steps_per_arcsec  # arcsec/s

    feasible = peak_rate_arcsec_s <= max_rate
    if feasible:
        rec = f"{target_name} requires {peak_rate_arcsec_s:.1f} arcsec/s. OAT max is {max_rate:.1f} arcsec/s. Tracking feasible."
    else:
        rec = (f"{target_name} moves at ~{peak_rate_arcsec_s:.0f} arcsec/s — the OAT maxes out at "
               f"~{max_rate:.0f} arcsec/s. Not trackable. Suggest photographing with a fixed wide field instead.")
    return TrackingFeasibility(
        feasible=feasible,
        target=target_name,
        peak_rate_arcsec_s=round(peak_rate_arcsec_s, 2),
        mount_max_rate_arcsec_s=round(max_rate, 2),
        recommendation=rec,
    )
