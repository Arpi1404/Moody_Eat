from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import re
import time
from dataclasses import dataclass
from collections.abc import Iterable

from config import Settings, get_settings
from models import (
    ALLOWED_NEARBY_TYPES,
    NearbyPlacesRequest,
    NearbyPlacesResponse,
    PlaceItem,
    ResolvedLocationOut,
)
from services.place_utils import attach_distances, dedupe_places
from services.places_exceptions import (
    LocationNotFoundError,
    PlacesProviderError,
    ProviderAuthError,
    ProviderQuotaError,
    ProviderTimeoutError,
)
from services.places_provider import PlacesProvider, RawPlace, ResolvedLocation

logger = logging.getLogger(__name__)
_DEFAULT_CATEGORY_SET = frozenset({"cafe", "restaurant"})
_TOKEN_RE = re.compile(r"[a-z_]+")
_INTENT_STOPWORDS = {
    "near",
    "nearby",
    "around",
    "at",
    "in",
    "me",
    "my",
    "current",
    "location",
    "find",
    "search",
    "for",
}
_CATEGORY_ALIASES = {
    "cafes": "cafe",
    "restaurants": "restaurant",
    "bars": "bar",
    "bakeries": "bakery",
}
_MIN_RATING = 3.5
_MIN_USER_RATINGS_TOTAL = 40


@dataclass
class _CacheEntry:
    expires_at: float
    response: NearbyPlacesResponse


class NearbyPlacesService:
    """Orchestrates geocode, multi-type nearby fetch, merge, rank, and response mapping."""

    def __init__(
        self,
        provider: PlacesProvider,
        settings: Settings | None = None,
    ) -> None:
        self._provider = provider
        self._settings = settings or get_settings()
        self._cache: dict[str, _CacheEntry] = {}
        self._cache_lock = asyncio.Lock()

    def _cache_key(
        self,
        req: NearbyPlacesRequest,
        *,
        categories: list[str],
        geocode_query: str,
    ) -> str:
        payload = {
            "q": geocode_query.strip().casefold(),
            "c": sorted({c.strip().casefold() for c in categories}),
            "r": req.radius_meters,
            "l": req.limit,
        }
        raw = json.dumps(payload, sort_keys=True).encode()
        return hashlib.sha256(raw).hexdigest()

    async def _get_cached(self, key: str) -> NearbyPlacesResponse | None:
        ttl = self._settings.cache_ttl_seconds
        if ttl <= 0:
            return None
        async with self._cache_lock:
            entry = self._cache.get(key)
            if not entry:
                return None
            if time.monotonic() >= entry.expires_at:
                del self._cache[key]
                return None
            return entry.response

    async def _set_cached(self, key: str, response: NearbyPlacesResponse) -> None:
        ttl = self._settings.cache_ttl_seconds
        if ttl <= 0:
            return
        async with self._cache_lock:
            if len(self._cache) > 2000:
                self._cache.clear()
            self._cache[key] = _CacheEntry(
                expires_at=time.monotonic() + float(ttl),
                response=response,
            )

    async def search(self, req: NearbyPlacesRequest) -> NearbyPlacesResponse:
        inferred_categories = self._infer_categories(req.query)
        categories = self._effective_categories(req.categories, inferred_categories)
        geocode_query = self._geocode_query(req.query, inferred_categories)
        key = self._cache_key(req, categories=categories, geocode_query=geocode_query)
        cached = await self._get_cached(key)
        if cached is not None:
            return cached

        resolved: ResolvedLocation = await self._provider.geocode(geocode_query)
        category_concurrency = max(1, int(self._settings.category_concurrency))
        semaphore = asyncio.Semaphore(category_concurrency)

        async def _fetch_category(cat: str) -> list[RawPlace]:
            async with semaphore:
                return await self._provider.nearby_by_type(
                    lat=resolved.lat,
                    lng=resolved.lng,
                    radius_meters=req.radius_meters,
                    place_type=cat,
                    target_count=req.limit,
                )

        batches = await asyncio.gather(*(_fetch_category(cat) for cat in categories))
        merged = [place for batch in batches for place in batch]

        unique = dedupe_places(merged)
        quality = self._quality_filter(unique)
        scored = attach_distances(resolved.lat, resolved.lng, quality)
        scored.sort(
            key=lambda pair: (
                -self._intent_match_score(pair[0], inferred_categories),
                -self._popularity_score(pair[0]),
                pair[1],  # tie-break toward closer options
            )
        )
        cap = min(req.limit, self._settings.max_limit)
        top = scored[:cap]

        places: list[PlaceItem] = []
        for raw, dist_m in top:
            places.append(
                PlaceItem(
                    name=raw.name,
                    address=raw.address or "",
                    lat=raw.lat,
                    lng=raw.lng,
                    distance_meters=round(dist_m, 1),
                    rating=raw.rating,
                    user_ratings_total=raw.user_ratings_total,
                    business_status=raw.business_status,
                    types=raw.types,
                    provider_id=raw.provider_id,
                )
            )

        out = NearbyPlacesResponse(
            resolved_location=ResolvedLocationOut(
                name=resolved.name,
                lat=resolved.lat,
                lng=resolved.lng,
            ),
            places=places,
            count=len(places),
        )
        await self._set_cached(key, out)
        return out

    @staticmethod
    def _query_tokens(query: str) -> list[str]:
        return [t for t in _TOKEN_RE.findall(query.casefold()) if t]

    @classmethod
    def _infer_categories(cls, query: str) -> list[str]:
        out: list[str] = []
        for token in cls._query_tokens(query):
            token = _CATEGORY_ALIASES.get(token, token)
            if token in ALLOWED_NEARBY_TYPES and token not in out:
                out.append(token)
        return out

    @staticmethod
    def _effective_categories(
        request_categories: Iterable[str],
        inferred_categories: list[str],
    ) -> list[str]:
        req = list(request_categories)
        if inferred_categories and frozenset(req) == _DEFAULT_CATEGORY_SET:
            # Preserve query mention order when narrowing default categories.
            return inferred_categories
        return req

    @classmethod
    def _geocode_query(cls, query: str, inferred_categories: list[str]) -> str:
        if not inferred_categories:
            return query
        blocked = set(inferred_categories) | _INTENT_STOPWORDS
        kept = []
        for token in cls._query_tokens(query):
            token = _CATEGORY_ALIASES.get(token, token)
            if token in blocked:
                continue
            kept.append(token)
        if not kept:
            return query
        return " ".join(kept)

    @staticmethod
    def _intent_match_score(place: RawPlace, inferred_categories: list[str]) -> int:
        if not inferred_categories:
            return 0
        place_types = {t.casefold() for t in (place.types or [])}
        name = place.name.casefold()
        score = 0
        for category in inferred_categories:
            if category in place_types:
                score += 3
            if category in name:
                score += 2
        return score

    @staticmethod
    def _popularity_score(place: RawPlace) -> float:
        rating = place.rating or 0.0
        ratings_total = max(0, int(place.user_ratings_total or 0))
        # Dampens viral outliers while still rewarding broad consensus.
        return rating * math.log1p(ratings_total)

    @staticmethod
    def _quality_filter(places: Iterable[RawPlace]) -> list[RawPlace]:
        strict: list[RawPlace] = []
        relaxed: list[RawPlace] = []
        for place in places:
            if place.business_status and place.business_status != "OPERATIONAL":
                continue
            relaxed.append(place)
            rating = place.rating if place.rating is not None else 0.0
            ratings_total = int(place.user_ratings_total or 0)
            if rating >= _MIN_RATING and ratings_total >= _MIN_USER_RATINGS_TOTAL:
                strict.append(place)
        # If strict keeps enough candidates, prefer it; otherwise fall back.
        return strict if len(strict) >= 5 else relaxed


def map_provider_error(exc: PlacesProviderError) -> tuple[int, str]:
    if isinstance(exc, LocationNotFoundError):
        return 404, str(exc)
    if isinstance(exc, ProviderAuthError):
        return 503, str(exc)
    if isinstance(exc, ProviderQuotaError):
        return 503, str(exc)
    if isinstance(exc, ProviderTimeoutError):
        return 504, str(exc)
    return 502, str(exc)
