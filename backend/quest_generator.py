"""Quest generation: place selection, haversine travel estimates, time scheduling."""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, time
from typing import NamedTuple

from models import (
    CostEstimate,
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

# ── Quest start time per occasion (hour, minute, 24-h) ───────────────────────

_START: dict[Occasion, tuple[int, int]] = {
    Occasion.date:    (19, 0),
    Occasion.friends: (20, 0),
    Occasion.solo:    (10, 0),
    Occasion.family:  (12, 0),
}

# ── Scoring weights (rating_w, proximity_w) per budget tier ──────────────────
# Remaining 0.15 is always log-popularity.
# cheap  → minimise distance, any good-enough rating
# mid    → balanced
# splurge → maximise quality, distance secondary

_WEIGHTS: dict[CostEstimate, tuple[float, float]] = {
    CostEstimate.cheap:   (0.35, 0.50),
    CostEstimate.mid:     (0.45, 0.40),
    CostEstimate.splurge: (0.60, 0.25),
}
_POP_W = 0.15

# ── Search expansion + quality bar ────────────────────────────────────────────
# Tried in order. Stop expanding once we have enough "strong" candidates.
_RADIUS_TIERS_M: tuple[int, ...] = (3_000, 6_000, 10_000)
_STRONG_RATING_FLOOR: float = 4.0
_STRONG_RATINGS_TOTAL_FLOOR: int = 100
_STRONG_TARGET_COUNT: int = 3

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

def _score(
    place: PlaceItem,
    cost: CostEstimate,
    prev_lat: float | None,
    prev_lng: float | None,
) -> float:
    rating_w, prox_w = _WEIGHTS[cost]

    rating_s = (place.rating or 0.0) / 5.0

    pop_raw = math.log1p(max(0, place.user_ratings_total or 0))
    pop_s = min(1.0, pop_raw / math.log1p(10_000))

    if prev_lat is not None and prev_lng is not None:
        d = haversine_m(prev_lat, prev_lng, place.lat, place.lng)
        # 1 km away → 0.5; 0 m → 1.0; 5 km → 0.17
        prox_s = 1.0 / (1.0 + d / 1_000.0)
    else:
        prox_s = 0.5  # neutral on first stop

    return rating_w * rating_s + prox_w * prox_s + _POP_W * pop_s


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


# ── why_this_place heuristic ──────────────────────────────────────────────────

def _why(place: PlaceItem, cost: CostEstimate, dist_m: float | None) -> str:
    notes: list[str] = []
    if place.rating and place.rating >= 4.3:
        notes.append(f"rated {place.rating:.1f}★ by locals")
    if dist_m is not None:
        if dist_m <= 600:
            notes.append("just a short walk away")
        elif dist_m <= _WALK_THRESHOLD_M:
            notes.append("an easy walk from the previous stop")
        else:
            notes.append("a quick ride from the previous stop")
    if cost == CostEstimate.splurge:
        notes.append("a quality pick for a splurge outing")
    elif cost == CostEstimate.cheap:
        notes.append("keeps the budget comfortable")
    if not notes:
        notes.append("a solid local choice")
    first_word = place.name.split()[0]
    return f"{first_word} — {', '.join(notes)}."


# ── Time scheduling ───────────────────────────────────────────────────────────

def _add_min(t: time, minutes: int) -> time:
    total = t.hour * 60 + t.minute + minutes
    return time(hour=(total // 60) % 24, minute=total % 60)


class _Slot(NamedTuple):
    tmpl: TemplateStop
    place: PlaceItem
    dist_from_prev_m: float | None


def _schedule(
    slots: list[_Slot],
    cost: CostEstimate,
    occasion: Occasion,
    duration_hours: float,
) -> list[Stop]:
    budget_min = int(duration_hours * 60)
    sh, sm = _START[occasion]
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

    # Scale dwell times down proportionally if total busts the budget
    total = sum(dwell) + sum(travel_mins)
    if total > budget_min:
        available = max(budget_min - sum(travel_mins), len(dwell) * 10)
        factor = available / max(sum(dwell), 1)
        dwell = [max(10, round(d * factor)) for d in dwell]

    stops: list[Stop] = []
    for i, slot in enumerate(slots):
        t_start = cursor
        t_end = _add_min(cursor, dwell[i])
        tp = travel_pairs[i]
        cursor = _add_min(t_end, travel_mins[i])

        stops.append(Stop(
            place=slot.place,
            category=slot.tmpl.category,
            time_block_start=t_start,
            time_block_end=t_end,
            travel_to_next_minutes=tp[0] if tp else None,
            travel_mode=tp[1] if tp else None,
            why_this_place=_why(slot.place, cost, slot.dist_from_prev_m),
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

    Returns the first tier with >=_STRONG_TARGET_COUNT strong picks. If no tier
    has enough strong picks, returns the broadest tier's full pool as fallback
    (still better than abandoning the stop).
    """
    fallback: list[PlaceItem] = []
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

        # Always remember the broadest non-empty tier as last-resort.
        fallback = result.places
        strong = [p for p in result.places if _is_strong(p)]
        if len(strong) >= _STRONG_TARGET_COUNT:
            logger.info(
                "Strong-pool hit type=%s radius=%dm strong=%d",
                place_type, radius, len(strong),
            )
            return strong

    if fallback:
        logger.info(
            "Falling back to broad pool for type=%s — no tier had %d strong picks",
            place_type, _STRONG_TARGET_COUNT,
        )
    return fallback


# ── Main orchestration ────────────────────────────────────────────────────────

async def assemble_quest(
    req: QuestGenerationRequest,
    service: NearbyPlacesService,
) -> Quest:
    template = TEMPLATES[req.occasion]
    used_ids: set[str] = set()
    slots: list[_Slot] = []
    prev_lat: float | None = None
    prev_lng: float | None = None

    for tmpl in template:
        place: PlaceItem | None = None
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

            picked = _pick(candidates, req.cost_estimate, prev_lat, prev_lng, used_ids)
            if picked is not None:
                place = picked
                break

        if place is None:
            logger.info(
                "All fallback types exhausted for stop category=%s in %r",
                tmpl.category,
                req.location,
            )
            continue

        dist_m = (
            haversine_m(prev_lat, prev_lng, place.lat, place.lng)
            if prev_lat is not None else None
        )
        slots.append(_Slot(tmpl=tmpl, place=place, dist_from_prev_m=dist_m))
        used_ids.add(place.provider_id)
        prev_lat, prev_lng = place.lat, place.lng

    if not slots:
        raise ValueError(
            f"No places could be found for any stop in {req.location!r}. "
            "Check that the location is recognisable and the Places API key is valid."
        )

    # Enrich picked places with today's opening/closing hours (concurrent).
    # Google's weekday convention: 0=Sunday, 1=Monday, ..., 6=Saturday.
    weekday_g = (datetime.now().weekday() + 1) % 7
    hours_results = await asyncio.gather(
        *(service.get_place_hours(s.place.provider_id, weekday_g) for s in slots),
        return_exceptions=True,
    )
    enriched_slots: list[_Slot] = []
    for slot, hours in zip(slots, hours_results):
        if isinstance(hours, BaseException):
            enriched_slots.append(slot)
            continue
        place_with_hours = slot.place.model_copy(update={
            "opens_today": hours.opens_today,
            "closes_today": hours.closes_today,
            "open_24h_today": hours.open_24h_today,
        })
        enriched_slots.append(_Slot(
            tmpl=slot.tmpl,
            place=place_with_hours,
            dist_from_prev_m=slot.dist_from_prev_m,
        ))
    slots = enriched_slots

    stops = _schedule(slots, req.cost_estimate, req.occasion, req.duration_hours)

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
        title=_TITLES[req.occasion][req.cost_estimate],
        occasion=req.occasion,
        stops=stops,
        total_duration_minutes=total_duration_minutes,
        total_cost_estimate=req.cost_estimate,
        narrative=narrative,
    )
