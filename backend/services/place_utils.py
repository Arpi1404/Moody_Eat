from __future__ import annotations

import math
import re
from collections.abc import Iterable

from services.places_provider import RawPlace

_EARTH_RADIUS_M = 6371000.0


def haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two WGS84 points in meters."""
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = math.sin(d_lat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(d_lng / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return _EARTH_RADIUS_M * c


_WS = re.compile(r"\s+")


def _norm_key(s: str) -> str:
    return _WS.sub(" ", s.strip().lower())


def dedupe_places(places: Iterable[RawPlace]) -> list[RawPlace]:
    """Prefer stable provider_id; otherwise name+address."""
    seen_ids: set[str] = set()
    seen_fuzzy: set[str] = set()
    out: list[RawPlace] = []
    for p in places:
        if p.provider_id:
            if p.provider_id in seen_ids:
                continue
            seen_ids.add(p.provider_id)
            out.append(p)
            continue
        key = _norm_key(f"{p.name}|{p.address}")
        if key in seen_fuzzy:
            continue
        seen_fuzzy.add(key)
        out.append(p)
    return out


def attach_distances(
    origin_lat: float,
    origin_lng: float,
    places: Iterable[RawPlace],
) -> list[tuple[RawPlace, float]]:
    scored: list[tuple[RawPlace, float]] = []
    for p in places:
        d = haversine_meters(origin_lat, origin_lng, p.lat, p.lng)
        scored.append((p, d))
    scored.sort(key=lambda x: x[1])
    return scored
