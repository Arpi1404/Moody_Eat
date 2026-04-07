from typing import Optional

from pydantic import BaseModel, Field, field_validator

# Google Places Nearby Search (legacy) `type` values we support for this API.
ALLOWED_NEARBY_TYPES = frozenset(
    {
        "restaurant",
        "cafe",
        "bar",
        "bakery",
        "meal_takeaway",
        "meal_delivery",
    }
)


class QuestRequest(BaseModel):
    location: str
    mood: str


class Cafe(BaseModel):
    name: str
    address: str
    distance_minutes_walk: int
    vibe: str


class QuestResponse(BaseModel):
    location: str
    mood: str
    cafes: list[Cafe]


class NearbyPlacesRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    categories: list[str] = Field(default_factory=lambda: ["cafe", "restaurant"])
    radius_meters: int = Field(default=3000, ge=100, le=10000)
    limit: int = Field(default=20, ge=1, le=20)

    @field_validator("categories")
    @classmethod
    def normalize_categories(cls, v: list[str]) -> list[str]:
        if not v:
            return ["cafe", "restaurant"]
        norm = [c.strip().lower() for c in v if c and str(c).strip()]
        if not norm:
            return ["cafe", "restaurant"]
        unsupported = sorted({c for c in norm if c not in ALLOWED_NEARBY_TYPES})
        if unsupported:
            allowed = ", ".join(sorted(ALLOWED_NEARBY_TYPES))
            raise ValueError(f"Unsupported categories: {unsupported}. Allowed: {allowed}")
        return norm


class ResolvedLocationOut(BaseModel):
    name: str
    lat: float
    lng: float


class PlaceItem(BaseModel):
    name: str
    address: str
    lat: float
    lng: float
    distance_meters: float
    rating: Optional[float] = None
    user_ratings_total: Optional[int] = None
    business_status: Optional[str] = None
    types: Optional[list[str]] = None
    provider_id: str


class NearbyPlacesResponse(BaseModel):
    resolved_location: ResolvedLocationOut
    places: list[PlaceItem]
    count: int

