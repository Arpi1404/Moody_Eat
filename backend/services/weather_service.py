"""Rain check for quest planning via Open-Meteo (free, no API key).

Fail-open by design: any error, timeout, or missing data returns None
("unknown"), and the generator plans exactly as before. Weather may only
ever *improve* a plan, never block one.
"""

from __future__ import annotations

import logging
import time

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
_cache: dict[tuple[float, float, int], tuple[float, bool | None]] = {}


def _window_max_probability(
    hourly: dict,
    start_hour: int,
    window_hours: int = _WINDOW_HOURS,
) -> int | None:
    """Max precipitation probability across [start_hour, start_hour+window)."""
    times = hourly.get("time") or []
    probs = hourly.get("precipitation_probability") or []
    max_p: int | None = None
    for t, p in zip(times, probs):
        if p is None:
            continue
        try:
            hour = int(str(t)[11:13])
        except (ValueError, IndexError):
            continue
        if start_hour <= hour < start_hour + window_hours:
            max_p = int(p) if max_p is None else max(max_p, int(p))
    return max_p


async def rain_expected(lat: float, lng: float, start_hour: int) -> bool | None:
    """True/False when the forecast is conclusive, None when unknown."""
    key = (round(lat, 1), round(lng, 1), start_hour)
    now = time.monotonic()
    hit = _cache.get(key)
    if hit is not None and now < hit[0]:
        return hit[1]

    result: bool | None = None
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(_REQUEST_TIMEOUT_S)) as client:
            r = await client.get(
                _FORECAST_URL,
                params={
                    "latitude": lat,
                    "longitude": lng,
                    "hourly": "precipitation_probability",
                    "forecast_days": 1,
                    "timezone": "auto",
                },
            )
            r.raise_for_status()
            data = r.json()
        max_p = _window_max_probability(data.get("hourly") or {}, start_hour)
        result = None if max_p is None else max_p >= RAIN_PROB_THRESHOLD
        logger.info(
            "weather_check lat=%.1f lng=%.1f start_hour=%d max_precip_prob=%s rainy=%s",
            lat, lng, start_hour, max_p, result,
        )
    except Exception as exc:
        logger.warning("weather_check_failed err_type=%s", exc.__class__.__name__)

    if len(_cache) > 500:
        _cache.clear()
    _cache[key] = (now + _CACHE_TTL_S, result)
    return result
