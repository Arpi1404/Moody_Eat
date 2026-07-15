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
    # From Places API (New) `servesVegetarianFood`. None = unknown (legacy
    # API, or Google has no data). True means veg options exist — NOT that
    # the kitchen is pure-veg; the quest generator treats it accordingly.
    serves_vegetarian_food: Optional[bool] = None
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
    title: str = Field(max_length=200)
    occasion: Occasion
    # Real quests have 1–4 stops; the cap only guards the public store
    # endpoint against oversized hand-crafted payloads.
    stops: list[Stop] = Field(max_length=10)
    total_duration_minutes: int
    total_cost_estimate: CostEstimate
    # Sum of per-stop estimates (stops without a price signal contribute 0).
    # None when no stop had any price signal.
    est_total_per_person_min_inr: Optional[int] = None
    est_total_per_person_max_inr: Optional[int] = None
    # Present when the rain forecast changed how the quest was planned.
    weather_note: Optional[str] = None
    # Present when a pure-veg request couldn't be fully confirmed from
    # Google's data — honesty over silence.
    veg_note: Optional[str] = None
    # Optional display name of the person who assembled a custom quest
    # ("Priya's Old City Crawl"). Never set on generated quests.
    created_by: Optional[str] = Field(default=None, max_length=60)
    narrative: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class StoredQuestCreateResponse(BaseModel):
    short_id: str
    # Path on the frontend origin; the client prefixes its own origin so the
    # backend never needs to know the canonical domain.
    path: str


class StoredQuestStats(BaseModel):
    short_id: str
    views: int
    created_at: str


class QuestGenerationRequest(BaseModel):
    location: str = Field(min_length=1, max_length=500)
    occasion: Occasion
    cost_estimate: CostEstimate
    people: int = Field(default=2, ge=1, le=20)
    # Legacy knob: when set, stop dwell times are scaled toward this many
    # hours. None (the default) keeps each stop's natural dwell — the plan is
    # as long as it honestly needs to be.
    duration_hours: Optional[float] = Field(default=None, ge=1.0, le=8.0)
    # When set, near-tied top candidates per stop are shuffled with this seed
    # ("regenerate" support). None keeps selection fully deterministic.
    variety_seed: Optional[int] = Field(default=None, ge=0, le=2**31 - 1)
    # Requested number of stops (1 = "just pick me one good place"). None
    # keeps the occasion default of 3.
    stop_count: Optional[int] = Field(default=None, ge=1, le=4)
    # When the outing starts. None keeps the occasion's default start time.
    # Opening-hours viability is checked against this, so a night quest will
    # never include a park that closes at sunset.
    day_part: Optional[DayPart] = None
    # Places from the user's recent quests: avoided when alternatives exist
    # (soft exclusion — never at the cost of an empty stop), so regulars see
    # variety instead of the same anchor spots every time.
    exclude_place_ids: list[str] = Field(default_factory=list, max_length=30)
    # Pure-veg mode: food stops require places Google marks as serving
    # vegetarian food (or whose name declares pure-veg); places explicitly
    # marked non-veg-only are rejected. Unknowns are a last resort, and the
    # quest carries a veg_note when confirmation wasn't possible everywhere.
    pure_veg: bool = False
