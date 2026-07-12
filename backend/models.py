import uuid
from datetime import datetime, time
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator

# Google Places Nearby Search (legacy) `type` values we support for this API.
ALLOWED_NEARBY_TYPES = frozenset(
    {
        # Food & drink
        "restaurant",
        "cafe",
        "bar",
        "bakery",
        "meal_takeaway",
        "meal_delivery",
        "night_club",
        # Attractions / outdoors
        "tourist_attraction",
        "park",
        "museum",
        "art_gallery",
        "zoo",
        "aquarium",
        # Activities / play
        "amusement_park",
        "bowling_alley",
        "movie_theater",
        "stadium",
        "shopping_mall",
        "spa",
        # Quiet / chill
        "book_store",
        "library",
    }
)


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
    # Google Places price_level: 0=free, 1=inexpensive, 2=moderate,
    # 3=expensive, 4=very expensive. None means unknown/unavailable.
    price_level: Optional[int] = Field(default=None, ge=0, le=4)
    # Per-person price range in INR from Places API (New). None when unknown.
    price_range_start_inr: Optional[int] = Field(default=None, ge=0)
    price_range_end_inr: Optional[int] = Field(default=None, ge=0)
    business_status: Optional[str] = None
    types: Optional[list[str]] = None
    provider_id: str
    # "HH:MM" 24-hour, today only. None when unknown or 24h.
    opens_today: Optional[str] = None
    closes_today: Optional[str] = None
    # True when the place is open 24h today.
    open_24h_today: bool = False


class NearbyPlacesResponse(BaseModel):
    resolved_location: ResolvedLocationOut
    places: list[PlaceItem]
    count: int


class PlaceBlurbIn(BaseModel):
    provider_id: str
    name: str
    types: list[str] = Field(default_factory=list)


class PlaceBlurbsRequest(BaseModel):
    mood: str
    budget: str
    people: int = Field(default=2, ge=1, le=50)
    places: list[PlaceBlurbIn] = Field(max_length=20)


class PlaceBlurbsResponse(BaseModel):
    blurbs: dict[str, str]


# ── Quest enums ────────────────────────────────────────────────────────────────

class Occasion(str, Enum):
    date = "date"
    friends = "friends"
    solo = "solo"
    family = "family"


class CostEstimate(str, Enum):
    cheap = "cheap"
    mid = "mid"
    splurge = "splurge"


class DayPart(str, Enum):
    morning = "morning"
    afternoon = "afternoon"
    evening = "evening"
    night = "night"


class TravelMode(str, Enum):
    walking = "walking"
    cycling = "cycling"
    transit = "transit"
    driving = "driving"


class StopCategory(str, Enum):
    cafe = "cafe"
    restaurant = "restaurant"
    bar = "bar"
    activity = "activity"
    attraction = "attraction"
    other = "other"


# ── Quest models ───────────────────────────────────────────────────────────────

class Stop(BaseModel):
    place: PlaceItem
    category: StopCategory
    time_block_start: time
    time_block_end: time
    # None on the final stop (no onward journey)
    travel_to_next_minutes: Optional[int] = None
    travel_mode: Optional[TravelMode] = None
    why_this_place: str
    # Estimated per-person spend at this stop in INR. None when no price signal
    # exists (e.g. parks, attractions). Where the estimate comes from is in
    # price_source: google_price_range | google_price_level | heuristic.
    est_cost_per_person_min_inr: Optional[int] = None
    est_cost_per_person_max_inr: Optional[int] = None
    price_source: Optional[str] = None


class StopSwapDelta(BaseModel):
    cost_change: int
    time_change_minutes: int
    distance_change_meters: int


class StopAlternative(Stop):
    delta: StopSwapDelta


class Quest(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    title: str
    occasion: Occasion
    stops: list[Stop]
    total_duration_minutes: int
    total_cost_estimate: CostEstimate
    # Sum of per-stop estimates (stops without a price signal contribute 0).
    # None when no stop had any price signal.
    est_total_per_person_min_inr: Optional[int] = None
    est_total_per_person_max_inr: Optional[int] = None
    narrative: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class QuestGenerationRequest(BaseModel):
    location: str = Field(min_length=1, max_length=500)
    occasion: Occasion
    cost_estimate: CostEstimate
    people: int = Field(default=2, ge=1, le=20)
    duration_hours: float = Field(default=3.0, ge=1.0, le=8.0)
    # When set, near-tied top candidates per stop are shuffled with this seed
    # ("regenerate" support). None keeps selection fully deterministic.
    variety_seed: Optional[int] = Field(default=None, ge=0, le=2**31 - 1)
    # Requested number of stops. None keeps the occasion default (3, with a
    # 4th auto-added for long outings).
    stop_count: Optional[int] = Field(default=None, ge=2, le=4)
    # When the outing starts. None keeps the occasion's default start time.
    # Opening-hours viability is checked against this, so a night quest will
    # never include a park that closes at sunset.
    day_part: Optional[DayPart] = None
