"""Rain check for quest planning via Open-Meteo (free, no API key).

Fail-open by design: any error, timeout, or missing data returns None
("unknown"), and the generator plans exactly as before. Weather may only
ever *improve* a plan, never block one.
"""

from __future__ import annotations

import logging
import time
from datetime import date

import httpx

logger = logging.getLogger(__name__)

_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_REQUEST_TIMEOUT_S = 4.0

# Precipitation probability (%) at or above which we call the window rainy.
RAIN_PROB_THRESHOLD = 60

# How many hours of the outing to check, from the quest start hour.
_WINDOW_HOURS = 4

# Stop types that are no fun in the rain. Deliberately only the certain ones —
# tourist_attraction is often indoors, so it stays.
OUTDOOR_TYPES = frozenset({"park", "zoo", "amusement_park"})

_CACHE_TTL_S = 1800.0
# Eight days of forecast: today plus the week a quest can be planned for.
_FORECAST_DAYS = 8
_cache: dict[tuple[float, float], tuple[float, dict | None]] = {}


def _window_max_probability(
    hourly: dict,
    start_hour: int,
    window_hours: int = _WINDOW_HOURS,
    on_date: date | None = None,
) -> int | None:
    """Max precipitation probability across [start_hour, start_hour+window)
    on `on_date` (the forecast's first day when None). Times are local."""
    times = hourly.get("time") or []
    probs = hourly.get("precipitation_probability") or []
    day = on_date.isoformat() if on_date is not None else (str(times[0])[:10] if times else "")
    max_p: int | None = None
    for t, p in zip(times, probs):
        if p is None or str(t)[:10] != day:
            continue
        try:
            hour = int(str(t)[11:13])
        except (ValueError, IndexError):
            continue
        if start_hour <= hour < start_hour + window_hours:
            max_p = int(p) if max_p is None else max(max_p, int(p))
    return max_p


async def _forecast(lat: float, lng: float) -> dict | None:
    """The hourly forecast for a spot, in its own time zone. Cached; None on
    any failure."""
    key = (round(lat, 1), round(lng, 1))
    now = time.monotonic()
    hit = _cache.get(key)
    if hit is not None and now < hit[0]:
        return hit[1]
    data: dict | None = None
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(_REQUEST_TIMEOUT_S)) as client:
            r = await client.get(
                _FORECAST_URL,
                params={
                    "latitude": lat,
                    "longitude": lng,
                    "hourly": "precipitation_probability,apparent_temperature",
                    "forecast_days": _FORECAST_DAYS,
                    "timezone": "auto",
                },
            )
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        logger.warning("weather_check_failed err_type=%s", exc.__class__.__name__)
    if len(_cache) > 500:
        _cache.clear()
    _cache[key] = (now + _CACHE_TTL_S, data)
    return data


async def rain_expected(
    lat: float, lng: float, start_hour: int, on_date: date | None = None
) -> bool | None:
    """True/False when the forecast is conclusive, None when unknown.

    `on_date` is the outing's day in the place's own calendar (today when
    None)."""
    data = await _forecast(lat, lng)
    if data is None:
        return None
    max_p = _window_max_probability(data.get("hourly") or {}, start_hour, on_date=on_date)
    result = None if max_p is None else max_p >= RAIN_PROB_THRESHOLD
    logger.info(
        "weather_check lat=%.1f lng=%.1f start_hour=%d max_precip_prob=%s rainy=%s",
        lat, lng, start_hour, max_p, result,
    )
    return result


async def utc_offset_minutes(lat: float, lng: float) -> int | None:
    """How far the spot's local time is ahead of UTC, from the same (cached)
    forecast call. None when the forecast could not be had."""
    data = await _forecast(lat, lng)
    if not data:
        return None
    seconds = data.get("utc_offset_seconds")
    if not isinstance(seconds, (int, float)):
        return None
    return int(seconds) // 60


async def feels_like_by_hour(
    lat: float, lng: float, on_date: date | None = None
) -> dict[int, float] | None:
    """The forecast feels-like temperature (°C) for each local hour of
    `on_date` (the forecast's first day when None), from the same cached call.
    None when the forecast could not be had."""
    data = await _forecast(lat, lng)
    if not data:
        return None
    hourly = data.get("hourly") or {}
    times = hourly.get("time") or []
    temps = hourly.get("apparent_temperature") or []
    day = on_date.isoformat() if on_date is not None else (str(times[0])[:10] if times else "")
    out: dict[int, float] = {}
    for t, v in zip(times, temps):
        if v is None or str(t)[:10] != day:
            continue
        try:
            out[int(str(t)[11:13])] = float(v)
        except (ValueError, IndexError):
            continue
    return out or None
