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
from services.places_provider import PlaceHours, PlacesProvider, RawPlace, ResolvedLocation

logger = logging.getLogger(__name__)

_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
_NEARBY_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"
_NEARBY_URL_NEW = "https://places.googleapis.com/v1/places:searchNearby"

# Every response field costs money: this mask keeps searchNearby in the cheapest
# SKU that still includes price data. Extend deliberately.
_NEARBY_FIELD_MASK_NEW = ",".join(
    (
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.rating",
        "places.userRatingCount",
        "places.types",
        "places.businessStatus",
        "places.priceLevel",
        "places.priceRange",
    )
)

_PRICE_LEVEL_NEW_TO_INT = {
    "PRICE_LEVEL_FREE": 0,
    "PRICE_LEVEL_INEXPENSIVE": 1,
    "PRICE_LEVEL_MODERATE": 2,
    "PRICE_LEVEL_EXPENSIVE": 3,
    "PRICE_LEVEL_VERY_EXPENSIVE": 4,
}


def _fmt_hhmm(g_time: str) -> str | None:
    """Google returns 'HHMM' (e.g. '0900', '2130'). Convert to 'HH:MM'."""
    if not g_time or len(g_time) != 4 or not g_time.isdigit():
        return None
    return f"{g_time[:2]}:{g_time[2:]}"


def _hours_for_weekday(periods: list[dict[str, Any]], weekday: int) -> PlaceHours:
    """Given Google's `opening_hours.periods` array, extract today's hours.

    A 24h place is signalled by a single period with day=0 time='0000' and no close.
    """
    if not periods:
        return PlaceHours(opens_today=None, closes_today=None, open_24h_today=False)

    # Detect 24h: single period, day 0, open time "0000", no close field.
    if len(periods) == 1:
        only = periods[0]
        opn = only.get("open") or {}
        if opn.get("day") == 0 and opn.get("time") == "0000" and "close" not in only:
            return PlaceHours(opens_today=None, closes_today=None, open_24h_today=True)

    for p in periods:
        opn = p.get("open") or {}
        if opn.get("day") == weekday:
            opens = _fmt_hhmm(str(opn.get("time") or ""))
            close = p.get("close") or {}
            closes = _fmt_hhmm(str(close.get("time") or "")) if close else None
            return PlaceHours(opens_today=opens, closes_today=closes, open_24h_today=False)

    return PlaceHours(opens_today=None, closes_today=None, open_24h_today=False)


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


def _map_new_api_http_error(status_code: int, body: dict[str, Any] | None) -> Exception:
    """Places API (New) signals errors via HTTP status + an `error` object."""
    err = (body or {}).get("error") or {}
    rpc_status = str(err.get("status") or "")
    message = str(err.get("message") or f"Nearby search (new) failed: HTTP {status_code}")
    if status_code == 429 or rpc_status == "RESOURCE_EXHAUSTED":
        return ProviderQuotaError("Places quota exceeded.", provider_status=rpc_status or "429")
    if status_code in (400, 401, 403) or rpc_status in ("PERMISSION_DENIED", "INVALID_ARGUMENT", "UNAUTHENTICATED"):
        if rpc_status == "PERMISSION_DENIED":
            message += " (Is 'Places API (New)' enabled for this key? Set PLACES_USE_NEW_API=false to fall back.)"
        return ProviderAuthError(message, provider_status=rpc_status or str(status_code))
    return PlacesProviderError(message, provider_status=rpc_status or str(status_code))


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

    async def _post_json_new(
        self,
        url: str,
        payload: dict[str, Any],
        field_mask: str,
    ) -> dict[str, Any]:
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": field_mask,
        }
        last_err: Exception | None = None
        retries = self._settings.provider_max_retries
        for attempt in range(retries + 1):
            start = time.perf_counter()
            try:
                async with self._client() as client:
                    r = await client.post(url, json=payload, headers=headers)
                elapsed_ms = (time.perf_counter() - start) * 1000
                logger.info(
                    "places_http url=%s status_code=%s elapsed_ms=%s",
                    url,
                    r.status_code,
                    round(elapsed_ms, 2),
                )
                if r.status_code >= 500 and attempt < retries:
                    await asyncio.sleep(0.2 * (attempt + 1))
                    continue
                if r.status_code >= 400:
                    try:
                        body = r.json()
                    except ValueError:
                        body = None
                    raise _map_new_api_http_error(r.status_code, body)
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
        target_count: int | None = None,
    ) -> list[RawPlace]:
        if self._settings.use_new_places_api:
            return await self._nearby_by_type_new(
                lat=lat,
                lng=lng,
                radius_meters=radius_meters,
                place_type=place_type,
                target_count=target_count,
            )
        return await self._nearby_by_type_legacy(
            lat=lat,
            lng=lng,
            radius_meters=radius_meters,
            place_type=place_type,
            target_count=target_count,
        )

    async def _nearby_by_type_new(
        self,
        *,
        lat: float,
        lng: float,
        radius_meters: int,
        place_type: str,
        target_count: int | None = None,
    ) -> list[RawPlace]:
        # searchNearby has no pagination; 20 is the API maximum per request.
        max_results = 20
        if target_count is not None and target_count > 0:
            max_results = max(1, min(20, target_count))
        payload: dict[str, Any] = {
            "includedTypes": [place_type],
            "maxResultCount": max_results,
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lng},
                    "radius": float(radius_meters),
                }
            },
        }
        data = await self._post_json_new(_NEARBY_URL_NEW, payload, _NEARBY_FIELD_MASK_NEW)
        return [self._raw_from_new_place(item) for item in data.get("places") or []]

    async def _nearby_by_type_legacy(
        self,
        *,
        lat: float,
        lng: float,
        radius_meters: int,
        place_type: str,
        target_count: int | None = None,
    ) -> list[RawPlace]:
        collected: list[RawPlace] = []
        next_token: str | None = None
        max_pages = max(1, min(3, int(self._settings.max_nearby_pages)))
        for _page in range(max_pages):
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
            if target_count is not None and target_count > 0 and len(collected) >= target_count:
                break
            next_token = data.get("next_page_token")
            if not next_token:
                break
        return collected

    async def place_hours(
        self,
        *,
        provider_id: str,
        weekday: int,
    ) -> PlaceHours:
        if not provider_id:
            return PlaceHours(opens_today=None, closes_today=None, open_24h_today=False)
        params = {
            "place_id": provider_id,
            "fields": "opening_hours",
            "key": self._api_key,
        }
        try:
            data = await self._request_json(_DETAILS_URL, params)
        except PlacesProviderError as exc:
            logger.warning("place_details_failed place_id=%s err=%s", provider_id, exc)
            return PlaceHours(opens_today=None, closes_today=None, open_24h_today=False)
        status = data.get("status", "")
        if status not in ("OK", "ZERO_RESULTS"):
            logger.warning("place_details_status status=%s place_id=%s", status, provider_id)
            return PlaceHours(opens_today=None, closes_today=None, open_24h_today=False)
        result = data.get("result") or {}
        oh = result.get("opening_hours") or {}
        periods = oh.get("periods") or []
        return _hours_for_weekday(periods, weekday)

    @staticmethod
    def _inr_units(money: dict[str, Any] | None) -> int | None:
        """Extract whole-rupee units from a google.type.Money object."""
        if not money:
            return None
        if str(money.get("currencyCode") or "") != "INR":
            return None
        units = money.get("units")
        try:
            return int(units) if units is not None else None
        except (TypeError, ValueError):
            return None

    @classmethod
    def _raw_from_new_place(cls, item: dict[str, Any]) -> RawPlace:
        loc = item.get("location") or {}
        display = item.get("displayName") or {}
        rating = item.get("rating")
        user_rating_count = item.get("userRatingCount")
        types = item.get("types")
        business_status = item.get("businessStatus")
        p_level = _PRICE_LEVEL_NEW_TO_INT.get(str(item.get("priceLevel") or ""))
        price_range = item.get("priceRange") or {}
        start_inr = cls._inr_units(price_range.get("startPrice"))
        end_inr = cls._inr_units(price_range.get("endPrice"))
        return RawPlace(
            provider_id=str(item.get("id") or ""),
            name=str(display.get("text") or "").strip(),
            address=str(item.get("formattedAddress") or "").strip(),
            lat=float(loc.get("latitude") or 0.0),
            lng=float(loc.get("longitude") or 0.0),
            rating=float(rating) if rating is not None else None,
            types=list(types) if isinstance(types, list) else None,
            user_ratings_total=int(user_rating_count) if user_rating_count is not None else None,
            business_status=str(business_status) if business_status else None,
            price_level=p_level,
            price_range_start_inr=start_inr,
            price_range_end_inr=end_inr,
        )

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
        price_level = item.get("price_level")
        p_level: int | None = int(price_level) if price_level is not None else None
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
            price_level=p_level,
        )
