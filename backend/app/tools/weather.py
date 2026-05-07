"""Weather and seeing conditions via Open-Meteo (no API key required)."""
import httpx
from typing import Optional
from app.config import get_settings

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


async def get_weather_and_seeing(lat: float = None, lng: float = None) -> dict:
    s = get_settings()
    lat = lat or s.observer_lat
    lng = lng or s.observer_lng

    params = {
        "latitude": lat,
        "longitude": lng,
        "current": "temperature_2m,relative_humidity_2m,cloud_cover,wind_speed_10m,precipitation",
        "hourly": "cloud_cover,temperature_2m,dew_point_2m,wind_speed_10m",
        "forecast_days": 1,
        "timezone": "UTC",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(OPEN_METEO_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    current = data.get("current", {})
    temp = current.get("temperature_2m", 0)
    humidity = current.get("relative_humidity_2m", 0)
    cloud = current.get("cloud_cover", 0)
    wind = current.get("wind_speed_10m", 0)
    precip = current.get("precipitation", 0)

    # Antoniadi seeing scale estimate (rough heuristic)
    seeing_score = _estimate_seeing(humidity, wind, cloud)

    return {
        "temperature_c": temp,
        "humidity_pct": humidity,
        "cloud_cover_pct": cloud,
        "wind_kmh": wind,
        "precipitation_mm": precip,
        "seeing_antoniadi": seeing_score,
        "seeing_description": _antoniadi_label(seeing_score),
        "astronomy_suitable": cloud < 30 and wind < 30 and precip == 0,
        "notes": _conditions_note(cloud, wind, humidity, precip),
    }


def _estimate_seeing(humidity: float, wind: float, cloud: float) -> int:
    """Estimate Antoniadi scale (I=perfect, V=terrible)."""
    if cloud > 80 or wind > 40:
        return 5
    score = 1
    if humidity > 80:
        score += 1
    if wind > 20:
        score += 1
    if cloud > 40:
        score += 1
    return min(score, 5)


def _antoniadi_label(score: int) -> str:
    labels = {
        1: "I — Perfect, without a quiver",
        2: "II — Slight undulations, calm periods",
        3: "III — Moderate seeing, some blurring",
        4: "IV — Poor seeing, constant troublesome undulations",
        5: "V — Very bad, hardly allows rough sketching",
    }
    return labels.get(score, "Unknown")


def _conditions_note(cloud: float, wind: float, humidity: float, precip: float) -> str:
    notes = []
    if precip > 0:
        notes.append("Rain/precipitation present — do not observe.")
    elif cloud > 70:
        notes.append("Heavy cloud cover — imaging not possible.")
    elif cloud > 30:
        notes.append("Partial cloud cover — intermittent sessions only.")
    else:
        notes.append("Clear skies — good for observing.")
    if wind > 30:
        notes.append(f"Strong wind ({wind:.0f} km/h) will cause mount vibration.")
    if humidity > 85:
        notes.append("High humidity — risk of dew on optics. Use dew heater.")
    return " ".join(notes)
