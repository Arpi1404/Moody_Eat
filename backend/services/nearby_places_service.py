from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import re
import time
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

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
from services.places_provider import PlaceHours, PlacesProvider, RawPlace, ResolvedLocation

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
_TYPE_DENYLIST = frozenset(
    {
        "travel_agency",
        "lodging",
        "real_estate_agency",
        "lawyer",
        "storage",
        "school",
        "finance",
        "home_goods_store",
        "insurance_agency",
        "meal_takeaway",
        "moving_company",
    }
)
_STORE_FOOD_CULTURE_TYPES = frozenset(
    {
        "restaurant",
        "cafe",
        "bakery",
        "bar",
        "book_store",
        "art_gallery",
        "museum",
    }
)
_NAME_DENYLIST_RE = re.compile(
    r"\b(?:stationery|xerox|wholesale|enterprises|traders|agency|consultancy|pvt\.?\s?ltd)\b"
    r"|(?<!\w)&\s*sons\b"
    r"|\(\s*mob[\.\s]"
    r"|\d{10}",
    re.IGNORECASE,
)
_BOOK_STORE_NAME_DENYLIST_RE = re.compile(
    r"\b(?:book|books)\s+"
    r"(?:gallery|seller|sellers|depot|depo|world|centre|center|stall|"
    r"mart|point|palace|hub|corner|land|house|stationer|stationers|shop)\b"
    r"|\bstationers?\b",
    re.IGNORECASE,
)
# A `book_store` that also carries the generic `store` tag is, in India, almost
# always a stationery / photocopy / generic shop that sells some notebooks.
# Real bookstores (Crossword, Blossom, Higginbothams) do not co-tag `store`.
# Require very high consensus to pass: 4.4★ AND 1,000+ reviews.
_BOOK_STORE_STATIONERY_MIN_RATING = 4.4
_BOOK_STORE_STATIONERY_MIN_RATINGS_TOTAL = 1000
_NOISY_TYPE_THRESHOLDS = {
    "book_store": (4.3, 300),
    "tourist_attraction": (4.3, 300),
}
_FILTER_RULES = (
    "business_status",
    "type_denylist",
    "store_without_food_culture",
    "book_store_stationery_combo",
    "name_denylist",
    "noisy_type_higher_bar",
    "strict_quality_bar",
)


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

    async def get_place_hours(self, provider_id: str, weekday: int) -> PlaceHours:
        """Pass-through to the provider's place_hours; safe to call for any place_id."""
        return await self._provider.place_hours(
            provider_id=provider_id,
            weekday=weekday,
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

        drop_counts: Counter[str] = Counter()
        filtered: list[RawPlace] = []
        for category, batch in zip(categories, batches):
            filtered.extend(
                self._quality_filter(
                    batch,
                    requested_place_type=category,
                    drop_counts=drop_counts,
                )
            )

        unique = dedupe_places(filtered)
        self._log_filter_counts(
            categories=categories,
            before_count=sum(len(batch) for batch in batches),
            after_count=len(unique),
            drop_counts=drop_counts,
        )
        scored = attach_distances(resolved.lat, resolved.lng, unique)
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
                    price_level=raw.price_level,
                    price_range_start_inr=raw.price_range_start_inr,
                    price_range_end_inr=raw.price_range_end_inr,
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
    def _log_filter_counts(
        *,
        categories: list[str],
        before_count: int,
        after_count: int,
        drop_counts: Counter[str],
    ) -> None:
        counts = {rule: int(drop_counts.get(rule, 0)) for rule in _FILTER_RULES}
        logger.info(
            "places_filter categories=%s before=%s after=%s drops=%s",
            ",".join(categories),
            before_count,
            after_count,
            counts,
        )

    @staticmethod
    def _quality_filter(
        places: Iterable[RawPlace],
        *,
        requested_place_type: str,
        drop_counts: Counter[str],
    ) -> list[RawPlace]:
        strict: list[RawPlace] = []
        for place in places:
            if place.business_status and place.business_status != "OPERATIONAL":
                drop_counts["business_status"] += 1
                continue

            place_types = {t.casefold() for t in (place.types or [])}
            if place_types & _TYPE_DENYLIST:
                drop_counts["type_denylist"] += 1
                continue

            if "store" in place_types and not (place_types & _STORE_FOOD_CULTURE_TYPES):
                drop_counts["store_without_food_culture"] += 1
                continue

            rating = place.rating if place.rating is not None else 0.0
            ratings_total = int(place.user_ratings_total or 0)

            # `book_store` + `store` co-tag is the Indian-stationery-shop tell.
            # Real bookstores have `book_store` without `store`.
            if (
                "book_store" in place_types
                and "store" in place_types
                and (
                    rating < _BOOK_STORE_STATIONERY_MIN_RATING
                    or ratings_total < _BOOK_STORE_STATIONERY_MIN_RATINGS_TOTAL
                )
            ):
                drop_counts["book_store_stationery_combo"] += 1
                continue

            if _NAME_DENYLIST_RE.search(place.name):
                drop_counts["name_denylist"] += 1
                continue

            if (
                "book_store" in place_types
                and _BOOK_STORE_NAME_DENYLIST_RE.search(place.name)
            ):
                drop_counts["name_denylist"] += 1
                continue

            noisy_threshold = _NOISY_TYPE_THRESHOLDS.get(requested_place_type)
            if noisy_threshold is not None and (
                rating < noisy_threshold[0]
                or ratings_total < noisy_threshold[1]
            ):
                drop_counts["noisy_type_higher_bar"] += 1
                continue

            if rating < _MIN_RATING or ratings_total < _MIN_USER_RATINGS_TOTAL:
                drop_counts["strict_quality_bar"] += 1
                continue

            strict.append(place)
        return strict


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
