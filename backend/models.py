import re
import unicodedata
import uuid
from datetime import datetime, time
from enum import Enum
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

# The two texts a quest's creator can write: a note on each stop and an intro.
# Mirrored in frontend/src/lib/creatorText.ts: change one, change both.
CREATOR_NOTE_MAX = 200
CREATOR_INTRO_MAX = 300
# Ceilings for the same two fields when the text is automatic or curated:
# curated notes run to 224 characters, curated intros to 518, and a
# model-written intro can be longer still. A quest over these cannot be shared
# or have its stops swapped, so they leave room.
STOP_NOTE_MAX = 300
NARRATIVE_MAX = 1500

# Control characters (newlines and tabs among them), line separators, and the
# marks that make text display in a different order from how it was typed.
_UNSAFE_TEXT_RE = re.compile(
    "[\x00-\x1f\x7f-\x9f\u2028\u2029\u202a-\u202e\u2066-\u2069]"
)


# Characters that take no room: they can hide inside a word or a web address,
# or make an empty note look written.
_ZERO_WIDTH_RE = re.compile("[\u200b-\u200d\u2060\ufeff]")


def _is_emoji_part(char: str) -> bool:
    return 0x1F000 <= ord(char) <= 0x1FAFF or unicodedata.category(char) == "So"


def _drop_zero_width(match: re.Match) -> str:
    """Remove one zero-width character, unless it is the joiner holding the
    parts of one emoji together, such as a family or a flag."""
    text, at = match.string, match.start()
    if match.group() == "\u200d" and 0 < at < len(text) - 1:
        before, after = text[at - 1], text[at + 1]
        if (before == "\ufe0f" or _is_emoji_part(before)) and _is_emoji_part(after):
            return match.group()
    return ""


def tidy_text(value: str) -> str:
    """One trimmed line: no control or zero-width characters, single spaces."""
    text = _ZERO_WIDTH_RE.sub(_drop_zero_width, value)
    return " ".join(_UNSAFE_TEXT_RE.sub(" ", text).split())


def _unset_marker(value: object) -> bool:
    """A by-creator marker is only written out when it is true, so a quest with
    no creator text is stored exactly as it was before the markers existed (and
    sharing it again still finds its existing link)."""
    return not value


def _fitting_text(value: str, limit: int) -> str:
    text = tidy_text(value)
    if len(text) > limit:
        raise ValueError(f"Keep this to {limit} characters or fewer.")
    return text


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
    # What Google says the place mainly is ("pizza_restaurant"). `types` lists
    # every tag, so a pizzeria that serves beer is also tagged "bar"; this is
    # the field that tells them apart. None when unknown.
    primary_type: Optional[str] = None
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


NAME_SEARCH_MIN_CHARS = 3


class NameSearchRequest(BaseModel):
    """A search for a place by its name, near the area a creator chose.

    Sent as a request body, not a query string, so that what was typed and
    where from do not end up in web server request logs.
    """

    q: str = Field(max_length=120)
    # The area's coordinates when known; otherwise `area`, which is geocoded.
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lng: Optional[float] = Field(default=None, ge=-180, le=180)
    area: Optional[str] = Field(default=None, max_length=500)

    @field_validator("q")
    @classmethod
    def tidy_query(cls, v: str) -> str:
        text = " ".join(v.split())
        if len(text) < NAME_SEARCH_MIN_CHARS:
            raise ValueError(f"Type at least {NAME_SEARCH_MIN_CHARS} characters.")
        return text


class LocationSuggestion(BaseModel):
    place_id: str
    # "Banjara Hills"
    main_text: str
    # "Hyderabad, Telangana, India"
    secondary_text: str = ""


class LocationSuggestionsResponse(BaseModel):
    suggestions: list[LocationSuggestion]


class SuggestionLocation(BaseModel):
    lat: float
    lng: float


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


# ── Stop kinds ─────────────────────────────────────────────────────────────────

class StopKind(str, Enum):
    """What a person can ask for when they swap a stop or add one."""

    meal = "meal"
    coffee = "coffee"
    dessert = "dessert"
    drinks = "drinks"
    walk = "walk"
    sights = "sights"
    movie = "movie"
    bowling = "bowling"


# kind -> (the one nearby-search type it asks for, the category the new stop
# gets). One type each, so choosing a kind costs one Places search. Every type
# must be in ALLOWED_NEARBY_TYPES. frontend/src/lib/stopKinds.ts lists the same
# kinds.
STOP_KIND_SEARCHES: dict[StopKind, tuple[str, StopCategory]] = {
    StopKind.meal: ("restaurant", StopCategory.restaurant),
    StopKind.coffee: ("cafe", StopCategory.cafe),
    StopKind.dessert: ("bakery", StopCategory.other),
    StopKind.drinks: ("bar", StopCategory.bar),
    StopKind.walk: ("park", StopCategory.attraction),
    StopKind.sights: ("tourist_attraction", StopCategory.attraction),
    StopKind.movie: ("movie_theater", StopCategory.activity),
    StopKind.bowling: ("bowling_alley", StopCategory.activity),
}

# A film outlasts the other activities, so it has a length of its own. Mirrors
# FILM_MINUTES in frontend/src/lib/questBuild.ts.
FILM_MINUTES = 150


# ── Quest models ───────────────────────────────────────────────────────────────

# How a quest's stops were chosen.
QuestOrigin = Literal["generated", "curated", "custom"]

# A Google place id. It ends up in upstream URL paths and in our own stores,
# hence the strict shape.
PLACE_ID_PATTERN = r"^[A-Za-z0-9_-]{10,400}$"
PlaceId = Annotated[str, StringConstraints(pattern=PLACE_ID_PATTERN)]

# Monday first. Mirrored in frontend/src/lib/closedDays.ts.
Weekday = Literal[
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
]


class ClosedDay(BaseModel):
    """A weekday a catalogue quest does not work, and the stop that is why."""

    day: Weekday
    stop_index: int = Field(ge=0, le=9)
    # Filled in from that stop. A saved copy can have its stops removed,
    # swapped or reordered, and the entry has to stay with the place.
    place_id: Optional[str] = Field(default=None, max_length=400)


class Stop(BaseModel):
    place: PlaceItem
    category: StopCategory
    time_block_start: time
    time_block_end: time
    # None on the final stop (no onward journey)
    travel_to_next_minutes: Optional[int] = None
    travel_mode: Optional[TravelMode] = None
    why_this_place: str
    # True when why_this_place is a note the quest's creator typed. Absent on
    # automatic lines, and on links stored before the field existed.
    note_by_creator: Optional[bool] = Field(default=None, exclude_if=_unset_marker)
    # Estimated per-person spend at this stop in INR. None when no price signal
    # exists (e.g. parks, attractions). Where the estimate comes from is in
    # price_source: google_price_range | google_price_level | heuristic.
    est_cost_per_person_min_inr: Optional[int] = None
    est_cost_per_person_max_inr: Optional[int] = None
    price_source: Optional[str] = None

    @field_validator("why_this_place")
    @classmethod
    def note_fits(cls, v: str) -> str:
        return _fitting_text(v, STOP_NOTE_MAX)

    @field_validator("note_by_creator")
    @classmethod
    def creator_note_fits(cls, v: Optional[bool], info) -> Optional[bool]:
        if v and len(info.data.get("why_this_place", "")) > CREATOR_NOTE_MAX:
            raise ValueError(f"Keep a note to {CREATOR_NOTE_MAX} characters or fewer.")
        return v


class StopSwapDelta(BaseModel):
    cost_change: int
    time_change_minutes: int
    distance_change_meters: int


class StopAlternative(Stop):
    delta: StopSwapDelta
    # Echoes the kind that was asked for. The quest page reads it to tell a
    # server that searched by kind from an older one that ignored the request.
    kind: Optional[StopKind] = None


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
    # True when `narrative` is an intro the quest's creator typed. Absent on
    # automatic text, and on links stored before the field existed.
    narrative_by_creator: Optional[bool] = Field(
        default=None, exclude_if=_unset_marker
    )

    # Weekdays on which a stop is shut. Set only on catalogue quests (and saved
    # or shared copies of them), and absent from the JSON when empty.
    closed_days: Optional[list[ClosedDay]] = Field(
        default=None, max_length=70, exclude_if=_unset_marker
    )

    @model_validator(mode="after")
    def closed_days_follow_their_stops(self) -> "Quest":
        """An entry written without a place id must name a stop that exists.

        One that has a place id came back from a browser, where the stops may
        have changed since: it moves with its place, and goes when the place
        has gone. Refusing the quest instead would stop an edited copy from
        being shared.
        """
        if not self.closed_days:
            return self
        place_ids = [stop.place.provider_id for stop in self.stops]
        kept: dict[tuple[str, int], ClosedDay] = {}
        for entry in self.closed_days:
            index = entry.stop_index
            if entry.place_id is None:
                if index >= len(place_ids):
                    raise ValueError(
                        f"closed_days names stop {index}, but the quest has "
                        f"{len(place_ids)} stops."
                    )
            elif index >= len(place_ids) or place_ids[index] != entry.place_id:
                if entry.place_id not in place_ids:
                    continue
                index = place_ids.index(entry.place_id)
            kept[(entry.day, index)] = entry.model_copy(
                update={"stop_index": index, "place_id": place_ids[index]}
            )
        self.closed_days = list(kept.values()) or None
        return self

    @field_validator("narrative")
    @classmethod
    def narrative_fits(cls, v: str, info) -> str:
        by_creator = info.data.get("narrative_by_creator")
        return _fitting_text(v, CREATOR_INTRO_MAX if by_creator else NARRATIVE_MAX)

    # Optional display name of the person who assembled a custom quest
    # ("Priya's Old City Crawl"). Never set on generated quests.
    created_by: Optional[str] = Field(default=None, max_length=60)
    # Who chose the stops: the engine, an editor, or the person themselves.
    # None on quests made before this field existed.
    origin: Optional[QuestOrigin] = None
    narrative: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SwapEvent(BaseModel):
    """One confirmed stop swap, as reported by the quest page.

    It says which suggested place was replaced by which, and for what kind of
    outing. It deliberately says nothing about the person or the quest: no
    quest id, no coordinates, no free text. Fields the model does not know are
    ignored, so a newer frontend can send more than an older backend stores.
    """

    from_place_id: PlaceId
    to_place_id: PlaceId
    # What the swap sheet offered, in the order shown. Knowing what was passed
    # over is what lets a choice be read as a preference.
    shown_place_ids: list[PlaceId] = Field(default_factory=list, max_length=12)
    occasion: Occasion
    category: StopCategory
    budget: CostEstimate
    stop_index: int = Field(ge=0, le=9)
    stop_count: int = Field(ge=1, le=10)
    # When the replaced stop was scheduled to start.
    slot_start: time
    quest_origin: Optional[QuestOrigin] = None

    @model_validator(mode="after")
    def _coherent(self) -> "SwapEvent":
        if self.from_place_id == self.to_place_id:
            raise ValueError("A swap needs two different places.")
        if self.stop_index >= self.stop_count:
            raise ValueError("stop_index is outside the quest.")
        return self


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
    # Free text ("Banjara Hills") or "lat,lng" when the user shared their
    # position — the search is anchored wherever this resolves to.
    location: str = Field(min_length=1, max_length=500)
    # Human-readable area for a "lat,lng" location ("Gachibowli, Hyderabad").
    # Display only: it names the quest and feeds the narrative, so raw
    # coordinates never end up in a title or a shared link.
    location_label: Optional[str] = Field(default=None, max_length=120)
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
