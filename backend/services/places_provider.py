from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ResolvedLocation:
    """Geocoded anchor point for nearby search."""

    name: str
    lat: float
    lng: float


@dataclass(frozen=True)
class RawPlace:
    """Normalized row from any places provider before distance ranking."""

    provider_id: str
    name: str
    address: str
    lat: float
    lng: float
    rating: float | None
    types: list[str] | None
    user_ratings_total: int | None = None
    business_status: str | None = None
    price_level: int | None = None
    # Per-person price range in INR from Places API (New) `priceRange`.
    # None when the provider has no range data (or the currency is not INR).
    price_range_start_inr: int | None = None
    price_range_end_inr: int | None = None
    # Places API (New) `servesVegetarianFood`. None when unknown (legacy API
    # or no Google data). True = veg options exist, not necessarily pure-veg.
    serves_vegetarian_food: bool | None = None


@dataclass(frozen=True)
class PlaceHours:
    """Opening hours for a single weekday. All times are local "HH:MM" 24-hour."""

    opens_today: str | None
    closes_today: str | None
    open_24h_today: bool


@runtime_checkable
class PlacesProvider(Protocol):
    async def geocode(self, query: str) -> ResolvedLocation:
        """Resolve free-text (or lat,lng string) to coordinates."""
        ...

    async def nearby_by_type(
        self,
        *,
        lat: float,
        lng: float,
        radius_meters: int,
        place_type: str,
        target_count: int | None = None,
    ) -> list[RawPlace]:
        """Places whose primary type matches `place_type` (provider-specific)."""
        ...

    async def place_hours(
        self,
        *,
        provider_id: str,
        weekday: int,
    ) -> PlaceHours:
        """Today's opening/closing time for the given place.

        weekday: 0=Sunday, 1=Monday, ..., 6=Saturday (Google convention).
        Returns all-None when hours are unknown.
        """
        ...
