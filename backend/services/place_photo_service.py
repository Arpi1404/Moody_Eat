"""Proxy Google Places photos so the API key is never exposed to the client."""

from __future__ import annotations

import logging
import time

import httpx

from config import get_settings

logger = logging.getLogger(__name__)

_CACHE: dict[str, tuple[bytes, str, float]] = {}
_CACHE_TTL = 3600

_DETAILS_URL_NEW = "https://places.googleapis.com/v1/places/{place_id}"
_MEDIA_URL_NEW = "https://places.googleapis.com/v1/{photo_name}/media"
_DETAILS_URL_LEGACY = "https://maps.googleapis.com/maps/api/place/details/json"
_PHOTO_URL_LEGACY = "https://maps.googleapis.com/maps/api/place/photo"


async def _fetch_new(client: httpx.AsyncClient, api_key: str, place_id: str, max_width: int) -> httpx.Response | None:
    headers = {"X-Goog-Api-Key": api_key}
    details_res = await client.get(
        _DETAILS_URL_NEW.format(place_id=place_id),
        headers={**headers, "X-Goog-FieldMask": "photos"},
    )
    if details_res.status_code >= 400:
        logger.warning(
            "place_photo_details_failed status=%s place_id=%s body=%s",
            details_res.status_code,
            place_id,
            details_res.text[:300],
        )
        return None
    photos = details_res.json().get("photos") or []
    photo_name = photos[0].get("name") if photos else None
    if not photo_name:
        return None
    return await client.get(
        _MEDIA_URL_NEW.format(photo_name=photo_name),
        params={"maxWidthPx": str(max(1, min(4800, max_width)))},
        headers=headers,
        follow_redirects=True,
    )


async def _fetch_legacy(client: httpx.AsyncClient, api_key: str, place_id: str, max_width: int) -> httpx.Response | None:
    details_res = await client.get(
        _DETAILS_URL_LEGACY,
        params={"place_id": place_id, "fields": "photos", "key": api_key},
    )
    details_res.raise_for_status()
    payload = details_res.json()
    if payload.get("status") not in ("OK", None):
        logger.warning("place_photo_details_failed status=%s place_id=%s", payload.get("status"), place_id)
        return None
    photos = (payload.get("result") or {}).get("photos")
    photo_ref = photos[0].get("photo_reference") if photos else None
    if not photo_ref:
        return None
    return await client.get(
        _PHOTO_URL_LEGACY,
        params={"photoreference": photo_ref, "maxwidth": str(max_width), "key": api_key},
        follow_redirects=True,
    )


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
    api_key = (settings.google_places_api_key or "").strip()
    if not api_key:
        return None

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            if settings.use_new_places_api:
                photo_res = await _fetch_new(client, api_key, place_id, max_width)
            else:
                photo_res = await _fetch_legacy(client, api_key, place_id, max_width)
            if photo_res is None:
                return None
            photo_res.raise_for_status()
            content_type = photo_res.headers.get("content-type", "image/jpeg")
            if not content_type.startswith("image/"):
                logger.warning("place_photo_not_image content_type=%s place_id=%s", content_type, place_id)
                return None
            data = photo_res.content
            _CACHE[cache_key] = (data, content_type, now + _CACHE_TTL)
            return data, content_type

    except httpx.HTTPError as exc:
        logger.warning("place_photo_failed place_id=%s err=%s", place_id, type(exc).__name__)
        return None
