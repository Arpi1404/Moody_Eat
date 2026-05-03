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
