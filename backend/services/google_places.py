from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from config import Settings, get_settings
from services.places_exceptions import (
    LocationNotFoundError,
    PlacesProviderError,
    ProviderAuthError,
    ProviderQuotaError,
    ProviderTimeoutError,
)
from services.places_provider import PlacesProvider, RawPlace, ResolvedLocation

logger = logging.getLogger(__name__)

_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
_NEARBY_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"


def _map_geocode_status(status: str, error_message: str | None) -> None:
    if status == "OK":
        return
    if status == "ZERO_RESULTS":
        raise LocationNotFoundError("No results for that location query.", provider_status=status)
    if status == "OVER_QUERY_LIMIT":
        raise ProviderQuotaError("Geocoding quota exceeded.", provider_status=status)
    if status in ("REQUEST_DENIED", "INVALID_REQUEST"):
        raise ProviderAuthError(
            error_message or f"Geocoding failed: {status}",
            provider_status=status,
        )
    raise PlacesProviderError(f"Geocoding failed: {status}", provider_status=status)


def _map_places_status(status: str, error_message: str | None) -> None:
    if status in ("OK", "ZERO_RESULTS"):
        return
    if status == "OVER_QUERY_LIMIT":
        raise ProviderQuotaError("Places quota exceeded.", provider_status=status)
    if status in ("REQUEST_DENIED", "INVALID_REQUEST"):
        raise ProviderAuthError(
            error_message or f"Nearby search failed: {status}",
            provider_status=status,
        )
    raise PlacesProviderError(f"Nearby search failed: {status}", provider_status=status)


class GooglePlacesProvider(PlacesProvider):
    """Google Geocoding API + Places Nearby Search (legacy JSON)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._api_key = (self._settings.google_places_api_key or "").strip()
        if not self._api_key:
            raise ProviderAuthError("GOOGLE_PLACES_API_KEY is not set.")

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=httpx.Timeout(self._settings.request_timeout_seconds))

    async def _request_json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        last_err: Exception | None = None
        retries = self._settings.provider_max_retries
        for attempt in range(retries + 1):
            start = time.perf_counter()
            try:
                async with self._client() as client:
                    r = await client.get(url, params=params)
                elapsed_ms = (time.perf_counter() - start) * 1000
                logger.info(
                    "places_http url=%s status_code=%s elapsed_ms=%s",
                    url.split("?")[0],
                    r.status_code,
                    round(elapsed_ms, 2),
                )
                if r.status_code >= 500 and attempt < retries:
                    await asyncio.sleep(0.2 * (attempt + 1))
                    continue
                r.raise_for_status()
                return r.json()
            except httpx.TimeoutException as e:
                last_err = e
                logger.warning("places_timeout attempt=%s", attempt)
                if attempt < retries:
                    await asyncio.sleep(0.2 * (attempt + 1))
                    continue
                raise ProviderTimeoutError("Upstream request timed out.") from e
            except httpx.HTTPError as e:
                last_err = e
                if attempt < retries:
                    await asyncio.sleep(0.2 * (attempt + 1))
                    continue
                raise PlacesProviderError("Upstream HTTP error.") from e
        raise PlacesProviderError("Upstream request failed.") from last_err

    async def geocode(self, query: str) -> ResolvedLocation:
        params = {"address": query.strip(), "key": self._api_key}
        data = await self._request_json(_GEOCODE_URL, params)
        status = data.get("status", "")
        err_msg = data.get("error_message")
        _map_geocode_status(status, err_msg)
        results = data.get("results") or []
        if not results:
            raise LocationNotFoundError("No geocoding results.", provider_status=status)
        first = results[0]
        loc = first.get("geometry", {}).get("location") or {}
        lat = float(loc["lat"])
        lng = float(loc["lng"])
        name = first.get("formatted_address") or query.strip()
        return ResolvedLocation(name=name, lat=lat, lng=lng)

    async def nearby_by_type(
        self,
        *,
        lat: float,
        lng: float,
        radius_meters: int,
        place_type: str,
    ) -> list[RawPlace]:
        collected: list[RawPlace] = []
        next_token: str | None = None
        for _page in range(3):
            params: dict[str, Any] = {
                "location": f"{lat},{lng}",
                "radius": str(radius_meters),
                "type": place_type,
                "key": self._api_key,
            }
            if next_token:
                params["pagetoken"] = next_token
                await asyncio.sleep(2.0)
            data = await self._request_json(_NEARBY_URL, params)
            status = data.get("status", "")
            err_msg = data.get("error_message")
            _map_places_status(status, err_msg)
            for item in data.get("results") or []:
                collected.append(self._raw_from_nearby_item(item))
            next_token = data.get("next_page_token")
            if not next_token:
                break
        return collected

    @staticmethod
    def _raw_from_nearby_item(item: dict[str, Any]) -> RawPlace:
        loc = item.get("geometry", {}).get("location") or {}
        lat = float(loc["lat"])
        lng = float(loc["lng"])
        address = (item.get("vicinity") or item.get("formatted_address") or "").strip()
        rating = item.get("rating")
        r_float: float | None = float(rating) if rating is not None else None
        user_ratings_total = item.get("user_ratings_total")
        ur_total: int | None = int(user_ratings_total) if user_ratings_total is not None else None
        types = item.get("types")
        t_list: list[str] | None = list(types) if isinstance(types, list) else None
        business_status = item.get("business_status")
        b_status: str | None = str(business_status) if business_status else None
        return RawPlace(
            provider_id=str(item.get("place_id") or ""),
            name=str(item.get("name") or "").strip(),
            address=address,
            lat=lat,
            lng=lng,
            rating=r_float,
            types=t_list,
            user_ratings_total=ur_total,
            business_status=b_status,
        )
