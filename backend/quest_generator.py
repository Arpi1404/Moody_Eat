"""Quest generation: place selection, haversine travel estimates, time scheduling."""

from __future__ import annotations

import logging
import math
import random
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, time
from typing import NamedTuple

from price_inference import (
    PRICE_SOURCE_GOOGLE_LEVEL,
    PRICE_SOURCE_GOOGLE_RANGE,
    PRICE_SOURCE_HEURISTIC,
    PRICE_SOURCE_UNKNOWN,
    estimate_cost_band,
    price_signal,
)
from models import (
    CostEstimate,
    DayPart,
    NearbyPlacesRequest,
    Occasion,
    PlaceItem,
    Quest,
    QuestGenerationRequest,
    Stop,
    StopCategory,
    TravelMode,
)
from quest_templates import (
    CAFE,
    DESSERT,
    DINNER_FAMILY,
    DRINKS,
    MAX_STOPS,
    MEAL,
    PLANS,
    SWEET_PRIMARY_TYPES,
    TREAT,
    TemplateStop,
)
from services.nearby_places_service import NearbyPlacesService
from services.place_blurbs_service import generate_quest_narrative
from services.places_exceptions import PlacesProviderError
from services.places_provider import PlaceHours, hours_for_weekday
from services.weather_service import OUTDOOR_TYPES, rain_expected

logger = logging.getLogger(__name__)

# ── Travel model ──────────────────────────────────────────────────────────────
# Mirrored in frontend/src/lib/questBuild.ts: change one, change both.

_WALK_M_PER_MIN: float = 80.0    # ≈ 4.8 km/h
_DRIVE_M_PER_MIN: float = 350.0  # ≈ 21 km/h in city traffic
# Distances are straight lines and the walk along real streets is longer, so
# the limit is kept short: 800 m is ten minutes on paper and nearer fifteen on
# foot.
_WALK_THRESHOLD_M: float = 800.0  # ≤ 800 m → walk; above → drive

# ── Dwell time per stop category (minutes) ────────────────────────────────────

_DWELL: dict[StopCategory, int] = {
    StopCategory.restaurant: 60,
    StopCategory.bar:        45,
    StopCategory.cafe:       40,
    StopCategory.activity:   60,
    StopCategory.attraction: 30,
    StopCategory.other:      30,
}

# Longest a stop may be stretched (as a multiple of its default dwell) when the
# user asks for a longer outing than the stops naturally fill.
_DWELL_STRETCH_CAP: float = 2.0

# Requests at or above this many hours get a fourth stop, since three stops
# can't plausibly fill a "6+ hr" outing even at maximum stretch.
_LONG_QUEST_HOURS: float = 5.5
# What a request with no stop_count gets. The planner sheet starts at the same
# number (HomePage's stopCount), so the two should move together.
_DEFAULT_STOP_COUNT: int = 2

# ── Quest start time per occasion (hour, minute, 24-h) ───────────────────────

_START: dict[Occasion, tuple[int, int]] = {
    Occasion.date:    (19, 0),
    Occasion.friends: (20, 0),
    Occasion.solo:    (10, 0),
    Occasion.family:  (12, 0),
}

# User-chosen start times (hour, minute). Overrides the occasion default, and
# hours viability is checked against these — a park that closes at sunset
# can't land in a night quest.
_DAY_PART_START: dict[DayPart, tuple[int, int]] = {
    DayPart.morning:   (10, 0),
    DayPart.afternoon: (13, 0),
    DayPart.evening:   (17, 30),
    DayPart.night:     (20, 0),
}


def _quest_start(req: QuestGenerationRequest) -> tuple[int, int]:
    if req.day_part is not None:
        return _DAY_PART_START[req.day_part]
    return _START[req.occasion]


def _spoken_day_part(req: QuestGenerationRequest) -> DayPart:
    """What a person would call the start time. Names the quest and its text."""
    if req.day_part is not None:
        return req.day_part
    hour = _START[req.occasion][0]
    if hour < 12:
        return DayPart.morning
    if hour < 17:
        return DayPart.afternoon
    if hour < 20:
        return DayPart.evening
    return DayPart.night


def _plan_day_part(req: QuestGenerationRequest) -> DayPart:
    """Which order of stops suits the start time.

    The same as the spoken day part except close to dinner: a request with no
    day part starts at the occasion's own time, and a date at 19:00 is an
    evening by name but opens with dinner, like a night plan.
    """
    if req.day_part is not None:
        return req.day_part
    hour, minute = _START[req.occasion]
    start = hour * 60 + minute
    if start < 11 * 60 + 30:
        return DayPart.morning
    if start < 16 * 60:
        return DayPart.afternoon
    if start < 18 * 60 + 45:
        return DayPart.evening
    return DayPart.night


# ── Meal hours ────────────────────────────────────────────────────────────────
# A plan that starts before a meal hour does not open with the meal (see
# quest_templates.PLANS), and the meal is held until the hour below. Nobody
# eats dinner at 17:30, and a kitchen that opens for dinner at 19:00 is shut
# until then, which leaves only the all-day chains to choose from.
_MEAL_NOT_BEFORE: dict[DayPart, tuple[int, int]] = {
    DayPart.morning: (12, 0),
    DayPart.evening: (19, 0),
}
# The wait is spent at the stop before the meal, which runs this much longer
# at most. A longer gap than this is left alone and the meal starts early:
# an hour and a half over one coffee is not a plan either.
_LINGER_MAX_MIN: int = 30
# A park, a zoo or a game of bowling stretches further than a coffee: up to an
# hour more, so that a family morning out reaches lunch at 12:00 rather than a
# kitchen that is not open yet at 11:30.
_LINGER_MAX_MIN_OUTING: int = 60
_LINGER_OUTING_CATEGORIES = frozenset({StopCategory.activity, StopCategory.attraction})
_LINGER_STEP_MIN: int = 5

# ── Scoring weights per budget tier ──────────────────────────────────────────
# Budget now means price fit, not "cheap places should merely be closer".
# Unknown Google price data is allowed, but receives lower confidence so it does
# not beat a clearly budget-matched place unless the rest of the signal is strong.

_SCORE_WEIGHTS: dict[CostEstimate, dict[str, float]] = {
    CostEstimate.cheap: {
        "quality": 0.30,
        "price_fit": 0.40,
        "route_fit": 0.22,
        "confidence": 0.08,
    },
    CostEstimate.mid: {
        "quality": 0.36,
        "price_fit": 0.30,
        "route_fit": 0.24,
        "confidence": 0.10,
    },
    CostEstimate.splurge: {
        "quality": 0.42,
        "price_fit": 0.32,
        "route_fit": 0.16,
        "confidence": 0.10,
    },
}

_UNKNOWN_PRICE_FIT = 0.58
_UNKNOWN_PRICE_CONFIDENCE = 0.45

# Past a few thousand reviews, more reviews say a place is busy, not that it
# is better. Uncapped, the most-reviewed chain in an area wins the food stop
# of every date and solo quest there. Capped for those two occasions, and only
# where the search is for food or drink: for a park or a sight the count is
# what tells the city's main park from a pocket park, so it stays.
_POPULARITY_FULL_AT_REVIEWS: int = 10_000
_POPULARITY_CAP_REVIEWS: int = 3_000
_POPULARITY_CAPPED_OCCASIONS = frozenset({Occasion.date, Occasion.solo})
_FOOD_SEARCH_TYPES = frozenset({"restaurant", "cafe", "bakery", "bar", "night_club"})


def _popularity_cap(occasion: Occasion, place_type: str) -> int | None:
    """The review count beyond which popularity adds nothing, if any."""
    if occasion in _POPULARITY_CAPPED_OCCASIONS and place_type in _FOOD_SEARCH_TYPES:
        return _POPULARITY_CAP_REVIEWS
    return None


# The opening stop has no previous stop to be near, so it is judged on how
# far it is from the spot that was searched. Anywhere within this distance
# counts the same; beyond it the fit falls away. Without this, a plan that
# opens with a park opens with the most popular park within 3 km, and every
# later stop follows it out of the area.
_FIRST_STOP_ROUTE_FIT: float = 0.66
_FIRST_STOP_NEAR_M: float = 1_500.0

# How sure we are the price level is right, by where it came from. Heuristic
# levels (type/name based) should lose to real Google data on close calls.
_PRICE_SOURCE_CONFIDENCE: dict[str, float] = {
    PRICE_SOURCE_GOOGLE_LEVEL: 1.0,
    PRICE_SOURCE_GOOGLE_RANGE: 0.95,
    PRICE_SOURCE_HEURISTIC: 0.65,
}

# Candidates scoring within this margin of the slot's best pick count as
# near-ties: a variety seed shuffles only within that group, so "regenerate"
# never trades away real quality.
_VARIETY_SCORE_EPSILON = 0.045

# On a cheap quest, a place *known* to be at this price level or above is
# rejected outright (kept only as a last resort when nothing cheaper exists).
# Score penalties alone let a stellar-but-pricey cafe outrank unknown-price
# budget spots, which breaks the "cheap" promise.
_CHEAP_REJECT_MIN_PRICE_LEVEL = 3

_PRICE_FIT: dict[CostEstimate, dict[int, float]] = {
    CostEstimate.cheap: {
        0: 0.95,
        1: 1.00,
        2: 0.62,
        3: 0.20,
        4: 0.08,
    },
    CostEstimate.mid: {
        0: 0.36,
        1: 0.72,
        2: 1.00,
        3: 0.72,
        4: 0.34,
    },
    CostEstimate.splurge: {
        0: 0.12,
        1: 0.28,
        2: 0.68,
        3: 1.00,
        4: 0.96,
    },
}

# ── Search expansion + quality bar ────────────────────────────────────────────
# Tried in order. Stop expanding once we have enough "strong" candidates.
_RADIUS_TIERS_M: tuple[int, ...] = (3_000, 6_000, 10_000)
_STRONG_RATING_FLOOR: float = 4.0
_STRONG_RATINGS_TOTAL_FLOOR: int = 100
_STRONG_TARGET_COUNT: int = 3
# How many candidates a stop tries when each one's hours cost a Place Details
# call. Places from a search on Places API (New) carry their hours, so all of
# them are tried for free (see _check_limit).
_VIABILITY_CHECK_LIMIT: int = 8
# Destination types most neighbourhoods simply don't have (around Kukatpally
# a zoo search returns nothing and an aquarium search only pet-fish shops, at
# every radius). For these the widest tier is searched first: results are
# popularity-ranked, so if nothing strong shows up within the full reach the
# nearer tiers won't have it either and are skipped — one paid search instead
# of three. When something is there, the usual near-to-far expansion runs and
# reuses the cached wide result, so picks are unchanged.
_SPARSE_PLACE_TYPES = frozenset({"zoo", "aquarium"})

# ── Meals chosen by what is wanted ────────────────────────────────────────────
# A type search for `restaurant` is ranked by size, so a date's dinner went to
# the area's busiest chain. For a date's meal the first search is instead a
# Text Search phrased by what the meal is for, which returns the places people
# go to for that. It replaces the `restaurant` type search; it does not add
# one, unless it finds too little and the stop falls back to that search.
#
# Only dates: for friends a busy, popular place is usually what is wanted, and
# a solo meal is rarely about the room. Text Search also has its own daily cap
# (1,000 requests), half that of Nearby Search.
#
# No cheap entries, on purpose: a cheap date keeps the type search. Asked for
# "affordable cozy" dinners, Text Search answered with moderate places
# (₹200–1,200 a head) where the type search found ₹1–200 ones, which changed
# what a plan labelled "Cheap" costs. To add cheap, the intent pool would need
# a price ceiling first: only places with a known price range starting at or
# below a set amount (say ₹300 a head) counting towards _INTENT_MIN_USABLE.
_INTENT_QUERIES: dict[tuple[Occasion, str], dict[CostEstimate, str]] = {
    (Occasion.date, "dinner"): {
        CostEstimate.mid: "romantic restaurant for a dinner date",
        CostEstimate.splurge: "fine dining restaurant for a romantic dinner",
    },
    (Occasion.date, "lunch"): {
        CostEstimate.mid: "nice restaurant for a lunch date",
        CostEstimate.splurge: "upscale restaurant for a lunch date",
    },
}
# Text Search leans towards the area but answers from well outside it: only
# places this close to the searched spot count, the reach of the first type
# search tier.
_INTENT_MAX_DISTANCE_M: float = 3_000.0
# Fewer usable places than this and the stop searches by type as before.
_INTENT_MIN_USABLE: int = 3
# How much Google's order counts: the best match gains this much score over
# the twentieth. About the gap between a 4.3 and a 4.6 rating, so the intent
# leads among places of similar standing without overriding budget or rating.
_INTENT_RANK_WEIGHT: float = 0.06
_INTENT_RANK_SPAN: int = 20
# Shuffle ("show me another") draws from a wider band in an intent pool. Every
# place in it was returned for what the meal is for, and the pool is small and
# spread out in price, so the type search's 0.045 band left most areas with
# one possible dinner.
_INTENT_VARIETY_SCORE_EPSILON: float = 0.09

# ── Mood-specific hard rejects ────────────────────────────────────────────────

_SOCIAL_EVENING_CUTOFF_MIN: int = 17 * 60
_PLACE_OF_WORSHIP_TYPES = frozenset(
    {
        "place_of_worship",
        "hindu_temple",
        "mosque",
        "church",
        "synagogue",
    }
)
_DATE_NAME_DENYLIST_RE = re.compile(
    r"\b(?:escape\s+rooms?|mystery\s+escape|lock\s+n\s+escape|rage\s+rooms?)\b",
    re.IGNORECASE,
)
_VIABILITY_RULES = (
    "already_used",
    "mood_type",
    "mood_name",
    "over_budget",
    "hours_unknown",
    "hours_closed",
)

# ── Quest title lookup ────────────────────────────────────────────────────────

# One title per time of day, in the order morning, afternoon, evening, night.
# A title that names a time ("An Evening Date") has to be true of the quest it
# is on; the ones that name none are the same all day.
_TITLES: dict[Occasion, dict[CostEstimate, tuple[str, str, str, str]]] = {
    Occasion.date: {
        CostEstimate.cheap: (
            "A Low-Key Date", "A Low-Key Date", "A Low-Key Date", "A Low-Key Date",
        ),
        CostEstimate.mid: (
            "A Morning Date", "An Afternoon Date", "An Evening Date", "A Date Night",
        ),
        CostEstimate.splurge: (
            "A Morning to Remember", "An Afternoon to Remember",
            "An Evening to Remember", "A Night to Remember",
        ),
    },
    Occasion.friends: {
        CostEstimate.cheap: (
            "A Budget Morning Out", "A Budget Afternoon Out",
            "A Budget Evening Out", "A Budget Night Out",
        ),
        CostEstimate.mid: (
            "A Morning with Friends", "An Afternoon with Friends",
            "An Evening with Friends", "A Night Out with Friends",
        ),
        CostEstimate.splurge: (
            "A Big Morning Out", "A Big Afternoon Out",
            "A Big Evening Out", "A Big Night Out",
        ),
    },
    Occasion.solo: {
        CostEstimate.cheap: (
            "A Solo Wander", "A Solo Wander", "A Solo Wander", "A Solo Wander",
        ),
        CostEstimate.mid: (
            "A Solo Day Out", "A Solo Day Out", "A Solo Evening Out", "A Solo Night Out",
        ),
        CostEstimate.splurge: (
            "A Solo Splurge Day", "A Solo Splurge Day",
            "A Solo Splurge Evening", "A Solo Splurge Night",
        ),
    },
    Occasion.family: {
        CostEstimate.cheap: (
            "A Family Day Out", "A Family Day Out",
            "A Family Evening Out", "A Family Night Out",
        ),
        CostEstimate.mid: (
            "A Family Outing", "A Family Outing", "A Family Outing", "A Family Outing",
        ),
        CostEstimate.splurge: (
            "A Family Treat Day", "A Family Treat Day",
            "A Family Treat Evening", "A Family Treat Night",
        ),
    },
}
_TITLE_ORDER = (DayPart.morning, DayPart.afternoon, DayPart.evening, DayPart.night)

_COORDS_RE = re.compile(r"^\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*$")


def _quest_title(
    occasion: Occasion,
    cost: CostEstimate,
    location: str,
    day_part: DayPart,
) -> str:
    """Base title plus the area, so two quests in the Saved list stay distinct."""
    base = _TITLES[occasion][cost][_TITLE_ORDER.index(day_part)]
    if _COORDS_RE.match(location):
        return base
    area = location.split(",")[0].strip()
    if not area or len(area) > 28:
        return base
    if area.islower():
        area = area.title()
    return f"{base} in {area}"


def _display_location(req: QuestGenerationRequest) -> str:
    """Where the quest is, in words — never raw coordinates.

    A location shared from the device arrives as "lat,lng" plus an optional
    readable label; anything shown to a person or sent to the narrative model
    uses the label (or a neutral phrase) instead of the numbers.
    """
    label = (req.location_label or "").strip()
    if label and not _COORDS_RE.match(label):
        return label
    if _COORDS_RE.match(req.location):
        return "your area"
    return req.location


# ── Haversine ─────────────────────────────────────────────────────────────────

def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in metres between two WGS-84 points."""
    R = 6_371_000.0
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δφ = math.radians(lat2 - lat1)
    Δλ = math.radians(lng2 - lng1)
    a = math.sin(Δφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(Δλ / 2) ** 2
    return 2.0 * R * math.asin(math.sqrt(min(1.0, a)))


def _travel_time(dist_m: float) -> tuple[int, TravelMode]:
    if dist_m <= _WALK_THRESHOLD_M:
        return max(1, round(dist_m / _WALK_M_PER_MIN)), TravelMode.walking
    return max(1, round(dist_m / _DRIVE_M_PER_MIN)), TravelMode.driving


# ── Place scoring and selection ───────────────────────────────────────────────

@dataclass(frozen=True)
class ScoreBreakdown:
    total: float
    quality: float
    price_fit: float
    route_fit: float
    confidence: float
    rating: float
    popularity: float
    price_level: int | None
    price_source: str


def _quality_score(
    place: PlaceItem,
    popularity_cap: int | None = None,
) -> tuple[float, float, float, float]:
    rating_s = (place.rating or 0.0) / 5.0
    reviews = max(0, place.user_ratings_total or 0)
    pop_raw = math.log1p(reviews)
    counted = reviews if popularity_cap is None else min(reviews, popularity_cap)
    pop_s = min(1.0, math.log1p(counted) / math.log1p(_POPULARITY_FULL_AT_REVIEWS))

    if place.rating is None:
        rating_s = 0.35

    quality = 0.76 * rating_s + 0.24 * pop_s
    quality_confidence = min(1.0, pop_raw / math.log1p(500))
    if place.rating is None:
        quality_confidence *= 0.35
    return quality, rating_s, pop_s, quality_confidence


def _price_fit_score(place: PlaceItem, cost: CostEstimate) -> tuple[float, float, str]:
    level, source = price_signal(place)
    if level is None:
        return _UNKNOWN_PRICE_FIT, _UNKNOWN_PRICE_CONFIDENCE, PRICE_SOURCE_UNKNOWN
    return _PRICE_FIT[cost][level], _PRICE_SOURCE_CONFIDENCE[source], source


def _first_stop_fit(distance_m: float) -> float:
    """Route fit for the opening stop, from its distance to the searched spot."""
    if distance_m <= _FIRST_STOP_NEAR_M:
        return _FIRST_STOP_ROUTE_FIT
    # 1.5 km -> 0.66; 3 km -> 0.33; 6 km -> 0.17
    return _FIRST_STOP_ROUTE_FIT / (1.0 + (distance_m - _FIRST_STOP_NEAR_M) / _FIRST_STOP_NEAR_M)


def _route_fit_score(
    place: PlaceItem,
    prev_lat: float | None,
    prev_lng: float | None,
) -> float:
    if prev_lat is None or prev_lng is None:
        # distance_meters is measured from the searched location.
        return _first_stop_fit(place.distance_meters)

    d = haversine_m(prev_lat, prev_lng, place.lat, place.lng)
    # 1 km away -> 0.5; 0 m -> 1.0; 5 km -> 0.17
    return 1.0 / (1.0 + d / 1_000.0)


def _score_breakdown(
    place: PlaceItem,
    cost: CostEstimate,
    prev_lat: float | None,
    prev_lng: float | None,
    *,
    popularity_cap: int | None = None,
) -> ScoreBreakdown:
    quality, rating_s, pop_s, quality_confidence = _quality_score(place, popularity_cap)
    price_fit, price_confidence, price_source = _price_fit_score(place, cost)
    route_fit = _route_fit_score(place, prev_lat, prev_lng)
    confidence = 0.60 * price_confidence + 0.40 * quality_confidence

    weights = _SCORE_WEIGHTS[cost]
    total = (
        weights["quality"] * quality
        + weights["price_fit"] * price_fit
        + weights["route_fit"] * route_fit
        + weights["confidence"] * confidence
    )
    if place.intent_rank is not None:
        total += _INTENT_RANK_WEIGHT * max(
            0.0, 1.0 - place.intent_rank / _INTENT_RANK_SPAN
        )
    return ScoreBreakdown(
        total=total,
        quality=quality,
        price_fit=price_fit,
        route_fit=route_fit,
        confidence=confidence,
        rating=rating_s,
        popularity=pop_s,
        price_level=place.price_level,
        price_source=price_source,
    )


def _score(
    place: PlaceItem,
    cost: CostEstimate,
    prev_lat: float | None,
    prev_lng: float | None,
    *,
    popularity_cap: int | None = None,
) -> float:
    return _score_breakdown(
        place, cost, prev_lat, prev_lng, popularity_cap=popularity_cap
    ).total


def _pick(
    candidates: list[PlaceItem],
    cost: CostEstimate,
    prev_lat: float | None,
    prev_lng: float | None,
    used: set[str],
    *,
    popularity_cap: int | None = None,
) -> PlaceItem | None:
    # Prefer unused places; relax if the pool would be empty
    pool = [p for p in candidates if p.provider_id not in used] or list(candidates)
    if not pool:
        return None
    return max(
        pool,
        key=lambda p: _score(p, cost, prev_lat, prev_lng, popularity_cap=popularity_cap),
    )


def _rank_unused(
    candidates: list[PlaceItem],
    cost: CostEstimate,
    prev_lat: float | None,
    prev_lng: float | None,
    used: set[str],
    *,
    popularity_cap: int | None = None,
) -> list[PlaceItem]:
    pool = [p for p in candidates if p.provider_id not in used]
    return sorted(
        pool,
        key=lambda p: _score(p, cost, prev_lat, prev_lng, popularity_cap=popularity_cap),
        reverse=True,
    )


def _variety_shuffle(
    ranked: list[PlaceItem],
    cost: CostEstimate,
    prev_lat: float | None,
    prev_lng: float | None,
    rng: random.Random,
    *,
    popularity_cap: int | None = None,
) -> list[PlaceItem]:
    """Shuffle only the leading near-tied group of an already-ranked list."""
    if len(ranked) < 2:
        return ranked
    scores = [
        _score(p, cost, prev_lat, prev_lng, popularity_cap=popularity_cap)
        for p in ranked
    ]
    from_intent = all(p.intent_rank is not None for p in ranked)
    cutoff = scores[0] - (
        _INTENT_VARIETY_SCORE_EPSILON if from_intent else _VARIETY_SCORE_EPSILON
    )
    group_end = 1
    while group_end < len(ranked) and scores[group_end] >= cutoff:
        group_end += 1
    if group_end <= 1:
        return ranked
    head = ranked[:group_end]
    rng.shuffle(head)
    return head + ranked[group_end:]


# ── why_this_place heuristic ──────────────────────────────────────────────────

def _why(place: PlaceItem, cost: CostEstimate, dist_m: float | None) -> str:
    notes: list[str] = []
    if place.rating and place.rating >= 4.3:
        notes.append(f"rated {place.rating:.1f}★ by locals")
    price_fit, _, price_source = _price_fit_score(place, cost)
    if price_source != "unknown":
        if price_fit >= 0.9:
            notes.append("matches the budget well")
        elif price_fit <= 0.35:
            notes.append("stretches the budget")
    if dist_m is not None:
        if dist_m <= 600:
            notes.append("just a short walk away")
        elif dist_m <= _WALK_THRESHOLD_M:
            notes.append("an easy walk from the previous stop")
        else:
            notes.append("a quick ride from the previous stop")
    if cost == CostEstimate.splurge and price_fit >= 0.68:
        notes.append("a quality pick for a splurge outing")
    elif cost == CostEstimate.cheap and price_fit >= 0.62:
        notes.append("keeps the budget comfortable")
    if not notes:
        notes.append("a solid local choice")
    line = ", ".join(notes)
    return f"{line[:1].upper()}{line[1:]}."


# ── Time scheduling ───────────────────────────────────────────────────────────

def _add_min(t: time, minutes: int) -> time:
    total = t.hour * 60 + t.minute + minutes
    return time(hour=(total // 60) % 24, minute=total % 60)


def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def _parse_hhmm(value: str | None) -> int | None:
    if value is None:
        return None
    parts = value.split(":", 1)
    if len(parts) != 2:
        return None
    hour_raw, minute_raw = parts
    if not (hour_raw.isdigit() and minute_raw.isdigit()):
        return None
    hour = int(hour_raw)
    minute = int(minute_raw)
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None
    return hour * 60 + minute


def _slot_fits_hours(place: PlaceItem, start: time, end: time) -> bool:
    if place.open_24h_today:
        return True
    return _slot_fits_window(place.opens_today, place.closes_today, start, end)


def _slot_fits_window(
    opens: str | None,
    closes: str | None,
    start: time,
    end: time,
) -> bool:
    """True when [start, end] sits inside one opens–closes window."""
    opens_at = _parse_hhmm(opens)
    closes_at = _parse_hhmm(closes)
    if opens_at is None or closes_at is None:
        return False

    start_min = _minutes(start)
    end_min = _minutes(end)
    if end_min <= start_min:
        end_min += 24 * 60

    if closes_at <= opens_at:
        closes_at += 24 * 60
        if start_min < opens_at:
            start_min += 24 * 60
            if end_min <= start_min:
                end_min += 24 * 60

    return opens_at <= start_min and end_min <= closes_at


def _mood_reject_rule(
    place: PlaceItem,
    occasion: Occasion,
    start: time,
) -> str | None:
    place_types = {t.casefold() for t in (place.types or [])}
    is_social_evening = (
        occasion in (Occasion.date, Occasion.friends)
        and _minutes(start) >= _SOCIAL_EVENING_CUTOFF_MIN
    )
    if is_social_evening and place_types & _PLACE_OF_WORSHIP_TYPES:
        return "mood_type"
    if occasion == Occasion.date and _DATE_NAME_DENYLIST_RE.search(place.name):
        return "mood_name"
    return None


def _hours_reject_rule(place: PlaceItem, start: time, end: time) -> str | None:
    if place.open_24h_today:
        return None
    if _parse_hhmm(place.opens_today) is None or _parse_hhmm(place.closes_today) is None:
        return "hours_unknown"
    if not _slot_fits_hours(place, start, end):
        return "hours_closed"
    return None


def _window_for_slot(
    hours: PlaceHours,
    start: time,
    end: time,
) -> tuple[str | None, str | None]:
    """The opening window that applies to a visit at [start, end].

    Many places close for part of the day — restaurants between lunch and
    dinner, parks from mid-morning to late afternoon. Judging an evening slot
    against the day's first window would call all of them closed, so pick the
    window the slot actually falls in. When none fits, the first window is
    returned and the slot is rejected as closed downstream.
    """
    for opens, closes in hours.windows:
        if _slot_fits_window(opens, closes, start, end):
            return opens, closes
    return hours.opens_today, hours.closes_today


def _wait_for_meal_hour(arrive: time, not_before: time | None, max_wait_min: int) -> int:
    """Minutes to hold a stop so it starts at `not_before`, up to the limit."""
    if not_before is None or max_wait_min <= 0:
        return 0
    gap = _minutes(not_before) - _minutes(arrive)
    # A negative gap is "already past the hour"; a huge one means the clock
    # wrapped past midnight, which is past the hour too.
    if gap <= 0 or gap > 12 * 60:
        return 0
    return min(gap, max_wait_min)


def _linger_room(
    place: PlaceItem,
    start: time,
    end: time,
    limit: int = _LINGER_MAX_MIN,
) -> int:
    """How much longer a visit can run before the place closes, in minutes.

    Capped at `limit`. Unknown hours do not hold a plan back, the same as
    everywhere else: they count as room to stay.
    """
    if place.open_24h_today:
        return limit
    if _parse_hhmm(place.opens_today) is None or _parse_hhmm(place.closes_today) is None:
        return limit
    for extra in range(limit, 0, -_LINGER_STEP_MIN):
        if _slot_fits_hours(place, start, _add_min(end, extra)):
            return extra
    return 0


async def _with_hours(
    place: PlaceItem,
    service: NearbyPlacesService,
    weekday_g: int,
    start: time,
    end: time,
    hours_memo: dict[str, PlaceHours] | None = None,
) -> PlaceItem:
    if place.opening_periods is not None:
        # The search brought the week's hours: no call. An empty list is a
        # place Google lists no hours for, and a lookup would say the same.
        hours = hours_for_weekday(place.opening_periods, weekday_g)
        opens, closes = _window_for_slot(hours, start, end)
        return place.model_copy(update={
            "opens_today": opens,
            "closes_today": closes,
            "open_24h_today": hours.open_24h_today,
        })
    # The fallback: a place whose search did not ask for hours (the legacy
    # API). A place can be looked at more than once in a request (both passes
    # over a stop, or two stops searching the same type). Each lookup is a
    # paid call, so the answer is kept for the length of the request.
    hours = hours_memo.get(place.provider_id) if hours_memo is not None else None
    if hours is None:
        logger.info("place_hours_fallback lookup=details")
        try:
            hours = await service.get_place_hours(place.provider_id, weekday_g)
        except Exception as exc:
            logger.warning(
                "place_hours_lookup_failed err_type=%s",
                exc.__class__.__name__,
            )
            return place
        if hours_memo is not None:
            hours_memo[place.provider_id] = hours
    opens, closes = _window_for_slot(hours, start, end)
    return place.model_copy(update={
        "opens_today": opens,
        "closes_today": closes,
        "open_24h_today": hours.open_24h_today,
    })


def _check_limit(ranked: list[PlaceItem]) -> int:
    """How many of a stop's ranked candidates to try.

    All of them when every one carries its hours from the search, since
    trying one then costs nothing; otherwise _VIABILITY_CHECK_LIMIT, which
    bounds the paid hours lookups.
    """
    if all(place.opening_periods is not None for place in ranked):
        return len(ranked)
    return _VIABILITY_CHECK_LIMIT


async def _pick_viable_candidate(
    candidates: list[PlaceItem],
    *,
    tmpl: TemplateStop,
    service: NearbyPlacesService,
    weekday_g: int,
    occasion: Occasion,
    cost: CostEstimate,
    cursor: time,
    prev_lat: float | None,
    prev_lng: float | None,
    used: set[str],
    requested_place_type: str,
    rng: random.Random | None = None,
    seen: frozenset[str] = frozenset(),
    popularity_cap: int | None = None,
    not_before: time | None = None,
    max_wait_min: int = 0,
    strict: bool = False,
    hours_memo: dict[str, PlaceHours] | None = None,
) -> _CandidatePick | None:
    """The best candidate that can actually be visited at this point in the plan.

    not_before / max_wait_min: hold the stop until a meal hour, by at most
    this many minutes (see _MEAL_NOT_BEFORE).
    strict: only a candidate that passes every check counts; the last-resort
    fallbacks below are not offered. Used for the first pass over a stop's
    fallback types, so that a clean pick from a later type beats a
    compromised pick from an earlier one.
    """
    # Recently-seen places (from the user's past quests) are avoided only
    # while fresh options exist — variety never costs a stop.
    ranked = _rank_unused(
        candidates, cost, prev_lat, prev_lng, used | seen, popularity_cap=popularity_cap
    )
    if not ranked and seen:
        ranked = _rank_unused(
            candidates, cost, prev_lat, prev_lng, used, popularity_cap=popularity_cap
        )
    if rng is not None:
        ranked = _variety_shuffle(
            ranked, cost, prev_lat, prev_lng, rng, popularity_cap=popularity_cap
        )
    drop_counts: Counter[str] = Counter()
    if len(ranked) < len(candidates):
        drop_counts["already_used"] = len(candidates) - len(ranked)
    price_known = sum(1 for p in ranked if price_signal(p).source != PRICE_SOURCE_UNKNOWN)

    # Weaker candidates kept aside and used only if every clean candidate
    # falls through: budget-fit places with unknown hours first (the budget
    # promise outranks hours certainty), then over-budget-but-open places.
    unknown_hours_fallback: _CandidatePick | None = None
    over_budget_fallback: _CandidatePick | None = None

    check_limit = _check_limit(ranked)
    for place in ranked[:check_limit]:
        dist_m = (
            haversine_m(prev_lat, prev_lng, place.lat, place.lng)
            if prev_lat is not None and prev_lng is not None
            else None
        )
        travel_minutes = _travel_time(dist_m)[0] if dist_m is not None else 0
        arrive = _add_min(cursor, travel_minutes)
        wait_min = _wait_for_meal_hour(arrive, not_before, max_wait_min)
        start = _add_min(arrive, wait_min)
        end = _add_min(start, _DWELL.get(tmpl.category, 30))

        mood_rule = _mood_reject_rule(place, occasion, start)
        if mood_rule is not None:
            drop_counts[mood_rule] += 1
            continue

        over_budget = (
            cost == CostEstimate.cheap
            and (level := price_signal(place).level) is not None
            and level >= _CHEAP_REJECT_MIN_PRICE_LEVEL
        )
        # An over-budget place is only ever a fallback, so once one is held
        # (or none is wanted) its hours are not worth checking.
        if over_budget and (strict or over_budget_fallback is not None):
            drop_counts["over_budget"] += 1
            continue

        place_with_hours = await _with_hours(
            place, service, weekday_g, start, end, hours_memo
        )
        hours_rule = _hours_reject_rule(place_with_hours, start, end)
        candidate = _CandidatePick(
            place=place_with_hours,
            dist_from_prev_m=dist_m,
            start=start,
            end=end,
            wait_min=wait_min,
        )
        if hours_rule == "hours_unknown" and not over_budget:
            drop_counts[hours_rule] += 1
            if unknown_hours_fallback is None:
                unknown_hours_fallback = candidate
            continue
        if hours_rule is not None:
            drop_counts[hours_rule] += 1
            continue

        if over_budget:
            drop_counts["over_budget"] += 1
            over_budget_fallback = candidate
            continue

        logger.info(
            "quest_candidate_viability type=%s category=%s checked=%d selected=true "
            "price_known=%d/%d drops=%s strict=%s",
            requested_place_type,
            tmpl.category.value,
            min(len(ranked), check_limit),
            price_known,
            len(ranked),
            {rule: int(drop_counts.get(rule, 0)) for rule in _VIABILITY_RULES},
            strict,
        )
        return candidate

    fallback = None if strict else (unknown_hours_fallback or over_budget_fallback)
    if fallback is unknown_hours_fallback and fallback is not None:
        selected_label = "hours_unknown_fallback"
    elif fallback is not None:
        selected_label = "over_budget_fallback"
    else:
        selected_label = "false"
    logger.info(
        "quest_candidate_viability type=%s category=%s checked=%d selected=%s "
        "price_known=%d/%d drops=%s strict=%s",
        requested_place_type,
        tmpl.category.value,
        min(len(ranked), check_limit),
        selected_label,
        price_known,
        len(ranked),
        {rule: int(drop_counts.get(rule, 0)) for rule in _VIABILITY_RULES},
        strict,
    )
    return fallback


class _Slot(NamedTuple):
    tmpl: TemplateStop
    place: PlaceItem
    dist_from_prev_m: float | None
    # Minutes spent here: the category's usual dwell, plus any time spent
    # waiting here for the next stop's meal hour.
    dwell_min: int
    start: time
    end: time


class _CandidatePick(NamedTuple):
    place: PlaceItem
    dist_from_prev_m: float | None
    start: time
    end: time
    # Minutes the previous stop has to run longer so this one starts at `start`.
    wait_min: int = 0


def _intent_query(tmpl: TemplateStop, req: QuestGenerationRequest) -> str | None:
    """The Text Search phrase for this stop, or None to search by type."""
    if tmpl.role != "meal":
        return None
    meal = "dinner" if tmpl.family is DINNER_FAMILY else "lunch"
    queries = _INTENT_QUERIES.get((req.occasion, meal))
    return queries.get(req.cost_estimate) if queries else None


async def _intent_candidates(
    service: NearbyPlacesService,
    tmpl: TemplateStop,
    req: QuestGenerationRequest,
    place_type: str,
) -> list[PlaceItem] | None:
    """Strong places for a meal from a search by intent, or None when the
    stop should search by type as before (no phrase for it, a failed search,
    or too few usable places)."""
    query = _intent_query(tmpl, req)
    if query is None:
        return None
    try:
        found = await service.search_by_intent(
            location=req.location,
            text=query,
            place_type=place_type,
            max_distance_m=_INTENT_MAX_DISTANCE_M,
        )
    except PlacesProviderError as exc:
        logger.warning("intent_search_failed err_type=%s", exc.__class__.__name__)
        return None
    strong = [p for p in found if _is_strong(p)]
    usable = [
        p for p in strong
        if tmpl.suits(p.name, p.primary_type, p.types)
        and p.provider_id not in req.exclude_place_ids
    ]
    if len(usable) < _INTENT_MIN_USABLE:
        logger.info(
            "intent_search_fallback role=%s found=%d usable=%d",
            tmpl.role, len(found), len(usable),
        )
        return None
    logger.info("intent_search_used role=%s usable=%d", tmpl.role, len(usable))
    return strong


async def _fill_stop(
    tmpl: TemplateStop,
    place_types: tuple[str, ...],
    *,
    req: QuestGenerationRequest,
    service: NearbyPlacesService,
    weekday_g: int,
    cursor: time,
    prev_lat: float | None,
    prev_lng: float | None,
    used: set[str],
    rng: random.Random | None,
    seen: frozenset[str],
    not_before: time | None,
    max_wait_min: int,
    hours_memo: dict[str, PlaceHours],
) -> _CandidatePick | None:
    """Pick a place for one stop of the plan, or None when nothing can be found.

    First pass, over the stop's whole list of fallback types: only places that
    are the kind the stop is for (TemplateStop.suits: their primary type
    belongs to the stop's family) and that pass every check. A search for
    `bar` returns the pizzeria that serves beer; this is what keeps it from
    winning the bar stop while a real bar exists anywhere in the list.

    Second pass, only when the first finds nothing: any place carrying the
    tag, with the usual last-resort fallbacks. A stop is never left empty for
    the sake of the first pass.
    """
    pools: dict[str, list[PlaceItem]] = {}

    async def _pick_from(
        candidates: list[PlaceItem],
        place_type: str,
        strict: bool,
    ) -> _CandidatePick | None:
        return await _pick_viable_candidate(
            candidates,
            tmpl=tmpl,
            service=service,
            weekday_g=weekday_g,
            occasion=req.occasion,
            cost=req.cost_estimate,
            cursor=cursor,
            prev_lat=prev_lat,
            prev_lng=prev_lng,
            used=used,
            requested_place_type=place_type,
            rng=rng,
            seen=seen,
            popularity_cap=_popularity_cap(req.occasion, place_type),
            not_before=not_before,
            max_wait_min=max_wait_min,
            strict=strict,
            hours_memo=hours_memo,
        )

    intent_pool: list[PlaceItem] | None = None
    if place_types:
        intent_pool = await _intent_candidates(service, tmpl, req, place_types[0])

    for index, place_type in enumerate(place_types):
        if index == 0 and intent_pool is not None:
            candidates = intent_pool
        else:
            candidates = await _search_with_expansion(service, req.location, place_type)
        pools[place_type] = candidates
        if not candidates:
            logger.info(
                "No places at any radius for type=%s — trying next fallback",
                place_type,
            )
            continue
        fitting = [
            p for p in candidates if tmpl.suits(p.name, p.primary_type, p.types)
        ]
        if not fitting:
            continue
        picked = await _pick_from(fitting, place_type, strict=True)
        if picked is not None:
            return picked

    for place_type, candidates in pools.items():
        if not candidates:
            continue
        picked = await _pick_from(candidates, place_type, strict=False)
        if picked is not None:
            logger.info(
                "quest_family_fallback role=%s type=%s primary_type=%s",
                tmpl.role,
                place_type,
                picked.place.primary_type,
            )
            return picked
    return None


def _schedule(
    slots: list[_Slot],
    cost: CostEstimate,
    start: tuple[int, int],
    duration_hours: float | None,
) -> list[Stop]:
    sh, sm = start
    cursor = time(hour=sh, minute=sm)

    # Compute travel between each consecutive pair of stops
    travel_pairs: list[tuple[int, TravelMode] | None] = []
    for i in range(len(slots)):
        if i + 1 < len(slots):
            d = haversine_m(
                slots[i].place.lat, slots[i].place.lng,
                slots[i + 1].place.lat, slots[i + 1].place.lng,
            )
            travel_pairs.append(_travel_time(d))
        else:
            travel_pairs.append(None)

    dwell = [s.dwell_min for s in slots]
    travel_mins = [tp[0] if tp else 0 for tp in travel_pairs]

    # Legacy path: when an explicit duration was requested, scale dwell times
    # proportionally toward it (stretching capped at 2x so a stop stays
    # plausible). Without one, each stop keeps its natural dwell and the total
    # duration is an output of the plan, not a promise.
    if duration_hours is not None:
        budget_min = int(duration_hours * 60)
        total = sum(dwell) + sum(travel_mins)
        if total > budget_min:
            available = max(budget_min - sum(travel_mins), len(dwell) * 10)
            factor = available / max(sum(dwell), 1)
            dwell = [max(10, round(d * factor)) for d in dwell]
        elif total < budget_min:
            available = budget_min - sum(travel_mins)
            factor = min(available / max(sum(dwell), 1), _DWELL_STRETCH_CAP)
            if factor > 1.0:
                dwell = [round(d * factor) for d in dwell]

    stops: list[Stop] = []
    for i, slot in enumerate(slots):
        t_start = cursor
        t_end = _add_min(cursor, dwell[i])
        tp = travel_pairs[i]
        cursor = _add_min(t_end, travel_mins[i])

        band = estimate_cost_band(slot.place)
        stops.append(Stop(
            place=slot.place,
            category=slot.tmpl.category,
            time_block_start=t_start,
            time_block_end=t_end,
            travel_to_next_minutes=tp[0] if tp else None,
            travel_mode=tp[1] if tp else None,
            why_this_place=_why(slot.place, cost, slot.dist_from_prev_m),
            est_cost_per_person_min_inr=band.min_inr if band else None,
            est_cost_per_person_max_inr=band.max_inr if band else None,
            price_source=band.source if band else None,
        ))
    return stops


# ── Search with progressive radius expansion ──────────────────────────────────

def _is_strong(p: PlaceItem) -> bool:
    """A place worth recommending: well-rated AND with broad consensus."""
    return (
        (p.rating or 0.0) >= _STRONG_RATING_FLOOR
        and (p.user_ratings_total or 0) >= _STRONG_RATINGS_TOTAL_FLOOR
    )


async def _search_tier(
    service: NearbyPlacesService,
    location: str,
    place_type: str,
    radius: int,
) -> list[PlaceItem] | None:
    """One radius tier of a type search. None means the provider failed."""
    try:
        result = await service.search(NearbyPlacesRequest(
            query=location,
            categories=[place_type],
            radius_meters=radius,
            limit=20,
        ))
    except PlacesProviderError as exc:
        logger.warning(
            "Places search failed type=%s radius=%dm location=%r: %s",
            place_type, radius, location, exc,
        )
        return None
    return result.places


async def _search_with_expansion(
    service: NearbyPlacesService,
    location: str,
    place_type: str,
) -> list[PlaceItem]:
    """Try increasing radii until we have at least a few strong candidates.

    Returns the first tier with >=_STRONG_TARGET_COUNT strong picks. Falls
    back to any strong picks at the broadest tier (still respecting the
    strong-quality floor). If no tier yields a single strong candidate,
    returns []: the template fallback chain will try the next place_type
    rather than admitting weak picks.
    """
    if place_type in _SPARSE_PLACE_TYPES:
        widest = await _search_tier(service, location, place_type, _RADIUS_TIERS_M[-1])
        if widest is not None and not any(_is_strong(p) for p in widest):
            logger.info(
                "Sparse type=%s has nothing strong within %dm — skipping nearer tiers",
                place_type, _RADIUS_TIERS_M[-1],
            )
            return []

    best_strong: list[PlaceItem] = []
    for radius in _RADIUS_TIERS_M:
        places = await _search_tier(service, location, place_type, radius)
        if not places:
            continue

        strong = [p for p in places if _is_strong(p)]
        if len(strong) >= _STRONG_TARGET_COUNT:
            logger.info(
                "Strong-pool hit type=%s radius=%dm strong=%d",
                place_type, radius, len(strong),
            )
            return strong
        if len(strong) > len(best_strong):
            best_strong = strong

    if best_strong:
        logger.info(
            "Partial strong-pool for type=%s strong=%d (below target=%d)",
            place_type, len(best_strong), _STRONG_TARGET_COUNT,
        )
    return best_strong


# ── Swapping a stop ───────────────────────────────────────────────────────────

def _swap_kind(stop: Stop, place_type: str, occasion: Occasion) -> TemplateStop | None:
    """The kind of stop being replaced, as far as a stored quest can tell.

    A quest does not record what each stop was for, only its category, so this
    reads the kind back from that. Used to offer the same kind of place first
    when a stop is swapped; None means no preference.
    """
    if stop.category == StopCategory.restaurant:
        return MEAL
    sweet = (stop.place.primary_type or "").casefold() in SWEET_PRIMARY_TYPES
    if stop.category == StopCategory.cafe and not sweet:
        return CAFE
    if stop.category == StopCategory.bar:
        return DRINKS
    # A dessert stop: "other" on quests made before dessert read as a café,
    # "cafe" at a bakery or sweet shop since.
    if (stop.category == StopCategory.other and place_type in ("bakery", "cafe")) or (
        stop.category == StopCategory.cafe and sweet
    ):
        return TREAT if occasion == Occasion.family else DESSERT
    return None


# ── Main orchestration ────────────────────────────────────────────────────────

async def assemble_quest(
    req: QuestGenerationRequest,
    service: NearbyPlacesService,
) -> Quest:
    if req.stop_count is not None:
        wanted = req.stop_count
    elif req.duration_hours is not None and req.duration_hours >= _LONG_QUEST_HOURS:
        wanted = MAX_STOPS
    else:
        wanted = _DEFAULT_STOP_COUNT
    plan_part = _plan_day_part(req)
    plan = PLANS[req.occasion][plan_part]
    template = plan.stops(wanted)
    meal_hour = _MEAL_NOT_BEFORE.get(plan_part)
    meal_not_before = time(*meal_hour) if meal_hour is not None else None
    # A plan that opens with the meal starts at the meal hour: a one-stop
    # evening date is dinner at 19:00, not at 17:30. The quest is still named
    # for the day part that was asked for.
    start_hm = _quest_start(req)
    if meal_hour is not None and template and template[0].role == "meal":
        start_hm = max(start_hm, meal_hour)

    used_ids: set[str] = set()
    seen_ids = frozenset(req.exclude_place_ids)
    slots: list[_Slot] = []
    hours_memo: dict[str, PlaceHours] = {}
    prev_lat: float | None = None
    prev_lng: float | None = None
    sh, sm = start_hm
    cursor = time(hour=sh, minute=sm)
    # Google's weekday convention: 0=Sunday, 1=Monday, ..., 6=Saturday.
    weekday_g = (datetime.now().weekday() + 1) % 7
    rng = random.Random(req.variety_seed) if req.variety_seed is not None else None

    # Rain check for the quest window (fail-open: unknown weather = no change).
    rain_risk: bool | None = None
    try:
        anchor = await service.resolve_location(req.location)
        rain_risk = await rain_expected(anchor.lat, anchor.lng, sh)
    except Exception as exc:
        logger.warning("weather_anchor_failed err_type=%s", exc.__class__.__name__)
    outdoor_skipped = False

    async def _place_stop(tmpl: TemplateStop) -> bool:
        """Fill one stop at the end of the plan so far. False when nothing fits."""
        nonlocal prev_lat, prev_lng, cursor, outdoor_skipped
        stop_place_types = tmpl.places_types
        if rain_risk:
            indoor_only = tuple(t for t in stop_place_types if t not in OUTDOOR_TYPES)
            # Only narrow when an indoor fallback exists — never empty a stop.
            if indoor_only and len(indoor_only) < len(stop_place_types):
                stop_place_types = indoor_only
                outdoor_skipped = True

        # A meal reached before its hour is held back, and the stop before it
        # runs longer by the same amount: the plan has no gaps, and the
        # frontend's reschedule (which keeps each stop's dwell) preserves it.
        not_before: time | None = None
        max_wait_min = 0
        if tmpl.role == "meal" and meal_not_before is not None and slots:
            not_before = meal_not_before
            before = slots[-1]
            max_wait_min = _linger_room(
                before.place,
                before.start,
                before.end,
                _LINGER_MAX_MIN_OUTING
                if before.tmpl.category in _LINGER_OUTING_CATEGORIES
                else _LINGER_MAX_MIN,
            )

        picked = await _fill_stop(
            tmpl,
            stop_place_types,
            req=req,
            service=service,
            weekday_g=weekday_g,
            cursor=cursor,
            prev_lat=prev_lat,
            prev_lng=prev_lng,
            used=used_ids,
            rng=rng,
            seen=seen_ids,
            not_before=not_before,
            max_wait_min=max_wait_min,
            hours_memo=hours_memo,
        )
        if picked is None:
            logger.info(
                "All fallback types exhausted for stop category=%s in %r",
                tmpl.category,
                req.location,
            )
            return False

        if picked.wait_min and slots:
            before = slots[-1]
            slots[-1] = before._replace(
                dwell_min=before.dwell_min + picked.wait_min,
                end=_add_min(before.end, picked.wait_min),
            )
        place = picked.place
        slots.append(_Slot(
            tmpl=tmpl,
            place=place,
            dist_from_prev_m=picked.dist_from_prev_m,
            dwell_min=_DWELL.get(tmpl.category, 30),
            start=picked.start,
            end=picked.end,
        ))
        used_ids.add(place.provider_id)
        prev_lat, prev_lng = place.lat, place.lng
        cursor = picked.end
        return True

    for tmpl in template:
        await _place_stop(tmpl)

    # A stop that could not be filled is made up from the plan's spares (what
    # a longer version of the same outing would have added), so that ordering
    # by time of day does not cost a sparse area a stop it used to get.
    if len(slots) < len(template):
        for tmpl in plan.spares(wanted):
            if len(slots) >= len(template):
                break
            await _place_stop(tmpl)

    where = _display_location(req)
    if not slots:
        raise ValueError(
            f"No places could be found for any stop in {where!r}. "
            "Check that the location is recognisable and the Places API key is valid."
        )

    stops = _schedule(slots, req.cost_estimate, start_hm, req.duration_hours)

    priced = [s for s in stops if s.est_cost_per_person_min_inr is not None]
    est_total_min = sum(s.est_cost_per_person_min_inr or 0 for s in priced) if priced else None
    est_total_max = sum(s.est_cost_per_person_max_inr or 0 for s in priced) if priced else None

    source_counts = Counter((s.price_source or PRICE_SOURCE_UNKNOWN) for s in stops)
    logger.info(
        "quest_price_profile cost=%s stops=%d sources=%s est_total_pp=%s-%s variety_seed=%s",
        req.cost_estimate.value,
        len(stops),
        dict(source_counts),
        est_total_min,
        est_total_max,
        req.variety_seed,
    )

    stop_summaries = [
        {
            "name": s.place.name,
            "category": s.category.value,
            "why": s.why_this_place,
        }
        for s in stops
    ]
    day_part = _spoken_day_part(req)
    narrative = await generate_quest_narrative(
        location=where,
        occasion=req.occasion.value,
        cost_estimate=req.cost_estimate.value,
        people=req.people,
        stop_summaries=stop_summaries,
        day_part=day_part.value,
    )

    # Total quest duration: first stop start → last stop end (crossing midnight handled)
    first_min = stops[0].time_block_start.hour * 60 + stops[0].time_block_start.minute
    last_min = stops[-1].time_block_end.hour * 60 + stops[-1].time_block_end.minute
    if last_min < first_min:
        last_min += 24 * 60  # crossed midnight
    total_duration_minutes = last_min - first_min

    return Quest(
        title=_quest_title(
            req.occasion,
            req.cost_estimate,
            (req.location_label or "").strip() or req.location,
            day_part,
        ),
        occasion=req.occasion,
        stops=stops,
        total_duration_minutes=total_duration_minutes,
        total_cost_estimate=req.cost_estimate,
        est_total_per_person_min_inr=est_total_min,
        est_total_per_person_max_inr=est_total_max,
        weather_note=(
            "Rain looks likely around your start time, so we kept the plan indoors."
            if outdoor_skipped
            else None
        ),
        origin="generated",
        narrative=narrative,
    )
