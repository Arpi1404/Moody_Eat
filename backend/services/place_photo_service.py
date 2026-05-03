"""Proxy Google Places photos so the API key is never exposed to the client."""

from __future__ import annotations

import time

import httpx

from config import get_settings

_CACHE: dict[str, tuple[bytes, str, float]] = {}
_CACHE_TTL = 3600


async def fetch_place_photo(
    place_id: str,
    max_width: int = 800,
) -> tuple[bytes, str] | None:
    """Return (image_bytes, content_type) for the first photo of a Google Place, or None."""
    cache_key = f"{place_id}:{max_width}"
    now = time.monotonic()
    if cache_key in _CACHE:
        data, ct, exp = _CACHE[cache_key]
        if now < exp:
            return data, ct

    settings = get_settings()
    api_key = settings.google_places_api_key
    if not api_key:
        return None

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            details_res = await client.get(
                "https://maps.googleapis.com/maps/api/place/details/json",
                params={"place_id": place_id, "fields": "photos", "key": api_key},
            )
            details_res.raise_for_status()
            photos = (details_res.json().get("result") or {}).get("photos")
            if not photos:
                return None
            photo_ref = photos[0].get("photo_reference")
            if not photo_ref:
                return None

            photo_res = await client.get(
                "https://maps.googleapis.com/maps/api/place/photo",
                params={"photoreference": photo_ref, "maxwidth": str(max_width), "key": api_key},
                follow_redirects=True,
            )
            photo_res.raise_for_status()
            content_type = photo_res.headers.get("content-type", "image/jpeg")
            data = photo_res.content
            _CACHE[cache_key] = (data, content_type, now + _CACHE_TTL)
            return data, content_type

    except httpx.HTTPError:
        return None
