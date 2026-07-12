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
from quest_templates import TEMPLATES, TemplateStop
from services.nearby_places_service import NearbyPlacesService
from services.place_blurbs_service import generate_quest_narrative
from services.places_exceptions import PlacesProviderError

logger = logging.getLogger(__name__)

# ── Travel model ──────────────────────────────────────────────────────────────

_WALK_M_PER_MIN: float = 80.0    # ≈ 4.8 km/h
_DRIVE_M_PER_MIN: float = 350.0  # ≈ 21 km/h in city traffic
_WALK_THRESHOLD_M: float = 1_400.0  # ≤ 1.4 km → walk; above → drive

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

_LONG_QUEST_EXTRA_STOP: dict[Occasion, TemplateStop] = {
    Occasion.date: TemplateStop(
        category=StopCategory.cafe,
        places_types=("cafe", "bakery"),
    ),
    Occasion.friends: TemplateStop(
        category=StopCategory.activity,
        places_types=("bowling_alley", "movie_theater", "shopping_mall", "tourist_attraction"),
    ),
    Occasion.solo: TemplateStop(
        category=StopCategory.cafe,
        places_types=("cafe", "bakery"),
    ),
    Occasion.family: TemplateStop(
        category=StopCategory.activity,
        places_types=("park", "museum", "tourist_attraction", "shopping_mall"),
    ),
}

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
_VIABILITY_CHECK_LIMIT: int = 8

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
    r"\b(?:escape\s+room|mystery\s+escape|lock\s+n\s+escape)\b",
    re.IGNORECASE,
)
_VIABILITY_RULES = (
    "already_used",
    "mood_type",
    "mood_name",
    "hours_unknown",
    "hours_closed",
)

# ── Quest title lookup ────────────────────────────────────────────────────────

_TITLES: dict[Occasion, dict[CostEstimate, str]] = {
    Occasion.date: {
        CostEstimate.cheap:   "A Low-Key Date",
        CostEstimate.mid:     "An Evening Date",
        CostEstimate.splurge: "A Night to Remember",
    },
    Occasion.friends: {
        CostEstimate.cheap:   "A Budget Night Out",
        CostEstimate.mid:     "A Night Out with Friends",
        CostEstimate.splurge: "A Big Night Out",
    },
    Occasion.solo: {
        CostEstimate.cheap:   "A Solo Wander",
        CostEstimate.mid:     "A Solo Day Out",
        CostEstimate.splurge: "A Solo Splurge Day",
    },
    Occasion.family: {
        CostEstimate.cheap:   "A Family Day Out",
        CostEstimate.mid:     "A Family Outing",
        CostEstimate.splurge: "A Family Treat Day",
    },
}

_COORDS_RE = re.compile(r"^\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*$")


def _quest_title(occasion: Occasion, cost: CostEstimate, location: str) -> str:
    """Base title plus the area, so two quests in the Saved list stay distinct."""
    base = _TITLES[occasion][cost]
    if _COORDS_RE.match(location):
        return base
    area = location.split(",")[0].strip()
    if not area or len(area) > 28:
        return base
    if area.islower():
        area = area.title()
    return f"{base} in {area}"


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


def _quality_score(place: PlaceItem) -> tuple[float, float, float, float]:
    rating_s = (place.rating or 0.0) / 5.0
    pop_raw = math.log1p(max(0, place.user_ratings_total or 0))
    pop_s = min(1.0, pop_raw / math.log1p(10_000))

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


def _route_fit_score(
    place: PlaceItem,
    prev_lat: float | None,
    prev_lng: float | None,
) -> float:
    if prev_lat is None or prev_lng is None:
        return 0.66

    d = haversine_m(prev_lat, prev_lng, place.lat, place.lng)
    # 1 km away -> 0.5; 0 m -> 1.0; 5 km -> 0.17
    return 1.0 / (1.0 + d / 1_000.0)


def _score_breakdown(
    place: PlaceItem,
    cost: CostEstimate,
    prev_lat: float | None,
    prev_lng: float | None,
) -> ScoreBreakdown:
    quality, rating_s, pop_s, quality_confidence = _quality_score(place)
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
) -> float:
    return _score_breakdown(place, cost, prev_lat, prev_lng).total


def _pick(
    candidates: list[PlaceItem],
    cost: CostEstimate,
    prev_lat: float | None,
    prev_lng: float | None,
    used: set[str],
) -> PlaceItem | None:
    # Prefer unused places; relax if the pool would be empty
    pool = [p for p in candidates if p.provider_id not in used] or list(candidates)
    if not pool:
        return None
    return max(pool, key=lambda p: _score(p, cost, prev_lat, prev_lng))


def _rank_unused(
    candidates: list[PlaceItem],
    cost: CostEstimate,
    prev_lat: float | None,
    prev_lng: float | None,
    used: set[str],
) -> list[PlaceItem]:
    pool = [p for p in candidates if p.provider_id not in used]
    return sorted(pool, key=lambda p: _score(p, cost, prev_lat, prev_lng), reverse=True)


def _variety_shuffle(
    ranked: list[PlaceItem],
    cost: CostEstimate,
    prev_lat: float | None,
    prev_lng: float | None,
    rng: random.Random,
) -> list[PlaceItem]:
    """Shuffle only the leading near-tied group of an already-ranked list."""
    if len(ranked) < 2:
        return ranked
    scores = [_score(p, cost, prev_lat, prev_lng) for p in ranked]
    cutoff = scores[0] - _VARIETY_SCORE_EPSILON
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

    opens_at = _parse_hhmm(place.opens_today)
    closes_at = _parse_hhmm(place.closes_today)
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


async def _with_hours(
    place: PlaceItem,
    service: NearbyPlacesService,
    weekday_g: int,
) -> PlaceItem:
    try:
        hours = await service.get_place_hours(place.provider_id, weekday_g)
    except Exception as exc:
        logger.warning(
            "place_hours_lookup_failed err_type=%s",
            exc.__class__.__name__,
        )
        return place
    return place.model_copy(update={
        "opens_today": hours.opens_today,
        "closes_today": hours.closes_today,
        "open_24h_today": hours.open_24h_today,
    })


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
) -> _CandidatePick | None:
    ranked = _rank_unused(candidates, cost, prev_lat, prev_lng, used)
    if rng is not None:
        ranked = _variety_shuffle(ranked, cost, prev_lat, prev_lng, rng)
    drop_counts: Counter[str] = Counter()
    if len(ranked) < len(candidates):
        drop_counts["already_used"] = len(candidates) - len(ranked)
    price_known = sum(1 for p in ranked if price_signal(p).source != PRICE_SOURCE_UNKNOWN)

    # A candidate whose hours Google doesn't know is a weaker pick than one we
    # can verify is open, but a better pick than an empty stop. Keep the best
    # one aside and use it only if every verifiable candidate falls through.
    unknown_hours_fallback: _CandidatePick | None = None

    for place in ranked[:_VIABILITY_CHECK_LIMIT]:
        dist_m = (
            haversine_m(prev_lat, prev_lng, place.lat, place.lng)
            if prev_lat is not None and prev_lng is not None
            else None
        )
        travel_minutes = _travel_time(dist_m)[0] if dist_m is not None else 0
        start = _add_min(cursor, travel_minutes)
        end = _add_min(start, _DWELL.get(tmpl.category, 30))

        mood_rule = _mood_reject_rule(place, occasion, start)
        if mood_rule is not None:
            drop_counts[mood_rule] += 1
            continue

        place_with_hours = await _with_hours(place, service, weekday_g)
        hours_rule = _hours_reject_rule(place_with_hours, start, end)
        if hours_rule == "hours_unknown":
            drop_counts[hours_rule] += 1
            if unknown_hours_fallback is None:
                unknown_hours_fallback = _CandidatePick(
                    place=place_with_hours,
                    dist_from_prev_m=dist_m,
                    start=start,
                    end=end,
                )
            continue
        if hours_rule is not None:
            drop_counts[hours_rule] += 1
            continue

        logger.info(
            "quest_candidate_viability type=%s category=%s checked=%d selected=true "
            "price_known=%d/%d drops=%s",
            requested_place_type,
            tmpl.category.value,
            min(len(ranked), _VIABILITY_CHECK_LIMIT),
            price_known,
            len(ranked),
            {rule: int(drop_counts.get(rule, 0)) for rule in _VIABILITY_RULES},
        )
        return _CandidatePick(
            place=place_with_hours,
            dist_from_prev_m=dist_m,
            start=start,
            end=end,
        )

    logger.info(
        "quest_candidate_viability type=%s category=%s checked=%d selected=%s "
        "price_known=%d/%d drops=%s",
        requested_place_type,
        tmpl.category.value,
        min(len(ranked), _VIABILITY_CHECK_LIMIT),
        "hours_unknown_fallback" if unknown_hours_fallback is not None else "false",
        price_known,
        len(ranked),
        {rule: int(drop_counts.get(rule, 0)) for rule in _VIABILITY_RULES},
    )
    return unknown_hours_fallback


class _Slot(NamedTuple):
    tmpl: TemplateStop
    place: PlaceItem
    dist_from_prev_m: float | None


class _CandidatePick(NamedTuple):
    place: PlaceItem
    dist_from_prev_m: float | None
    start: time
    end: time


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

    dwell = [_DWELL.get(s.tmpl.category, 30) for s in slots]
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
    best_strong: list[PlaceItem] = []
    for radius in _RADIUS_TIERS_M:
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
            continue

        if not result.places:
            continue

        strong = [p for p in result.places if _is_strong(p)]
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


# ── Main orchestration ────────────────────────────────────────────────────────

async def assemble_quest(
    req: QuestGenerationRequest,
    service: NearbyPlacesService,
) -> Quest:
    template = list(TEMPLATES[req.occasion])
    if req.stop_count is not None:
        # Explicit choice wins. 1-2 keeps the occasion's anchor stop(s);
        # 4 adds the same extra stop long quests get.
        if req.stop_count <= 2:
            template = template[:req.stop_count]
        elif req.stop_count == 4:
            template.insert(2, _LONG_QUEST_EXTRA_STOP[req.occasion])
    elif req.duration_hours is not None and req.duration_hours >= _LONG_QUEST_HOURS:
        template.insert(2, _LONG_QUEST_EXTRA_STOP[req.occasion])
    used_ids: set[str] = set()
    slots: list[_Slot] = []
    prev_lat: float | None = None
    prev_lng: float | None = None
    sh, sm = _quest_start(req)
    cursor = time(hour=sh, minute=sm)
    # Google's weekday convention: 0=Sunday, 1=Monday, ..., 6=Saturday.
    weekday_g = (datetime.now().weekday() + 1) % 7
    rng = random.Random(req.variety_seed) if req.variety_seed is not None else None

    for tmpl in template:
        picked: _CandidatePick | None = None
        for place_type in tmpl.places_types:
            candidates = await _search_with_expansion(
                service, req.location, place_type
            )
            if not candidates:
                logger.info(
                    "No places at any radius for type=%s — trying next fallback",
                    place_type,
                )
                continue

            picked = await _pick_viable_candidate(
                candidates,
                tmpl=tmpl,
                service=service,
                weekday_g=weekday_g,
                occasion=req.occasion,
                cost=req.cost_estimate,
                cursor=cursor,
                prev_lat=prev_lat,
                prev_lng=prev_lng,
                used=used_ids,
                requested_place_type=place_type,
                rng=rng,
            )
            if picked is not None:
                break

        if picked is None:
            logger.info(
                "All fallback types exhausted for stop category=%s in %r",
                tmpl.category,
                req.location,
            )
            continue

        place = picked.place
        slots.append(_Slot(
            tmpl=tmpl,
            place=place,
            dist_from_prev_m=picked.dist_from_prev_m,
        ))
        used_ids.add(place.provider_id)
        prev_lat, prev_lng = place.lat, place.lng
        cursor = picked.end

    if not slots:
        raise ValueError(
            f"No places could be found for any stop in {req.location!r}. "
            "Check that the location is recognisable and the Places API key is valid."
        )

    stops = _schedule(slots, req.cost_estimate, _quest_start(req), req.duration_hours)

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
    narrative = await generate_quest_narrative(
        location=req.location,
        occasion=req.occasion.value,
        cost_estimate=req.cost_estimate.value,
        people=req.people,
        stop_summaries=stop_summaries,
    )

    # Total quest duration: first stop start → last stop end (crossing midnight handled)
    first_min = stops[0].time_block_start.hour * 60 + stops[0].time_block_start.minute
    last_min = stops[-1].time_block_end.hour * 60 + stops[-1].time_block_end.minute
    if last_min < first_min:
        last_min += 24 * 60  # crossed midnight
    total_duration_minutes = last_min - first_min

    return Quest(
        title=_quest_title(req.occasion, req.cost_estimate, req.location),
        occasion=req.occasion,
        stops=stops,
        total_duration_minutes=total_duration_minutes,
        total_cost_estimate=req.cost_estimate,
        est_total_per_person_min_inr=est_total_min,
        est_total_per_person_max_inr=est_total_max,
        narrative=narrative,
    )
