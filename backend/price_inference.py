"""Price signals for places: Google data first, Hyderabad heuristics as fallback.

Resolution order (strongest signal wins):
1. Google `priceLevel`        -> source "google_price_level"
2. Google `priceRange` (INR)  -> source "google_price_range"
3. Type/name heuristics       -> source "heuristic"
4. Nothing                    -> source "unknown"
"""

from __future__ import annotations

import re
from typing import NamedTuple

from models import PlaceItem

PRICE_SOURCE_GOOGLE_LEVEL = "google_price_level"
PRICE_SOURCE_GOOGLE_RANGE = "google_price_range"
PRICE_SOURCE_HEURISTIC = "heuristic"
PRICE_SOURCE_UNKNOWN = "unknown"

# Per-person spend bands (INR) representative of each Google price level in
# Hyderabad. Used to render an estimate when only a level (no range) is known.
PRICE_LEVEL_BANDS_INR: dict[int, tuple[int, int]] = {
    0: (0, 0),
    1: (100, 350),
    2: (350, 900),
    3: (900, 1800),
    4: (1800, 3500),
}

# Midpoint-of-range thresholds for deriving a level from an INR price range.
# Aligned with the band table above.
_RANGE_LEVEL_THRESHOLDS_INR: tuple[tuple[int, int], ...] = (
    (350, 1),
    (900, 2),
    (1800, 3),
)

# Places API (New) types that carry a strong price connotation. Deliberately
# small and high-precision; anything ambiguous stays unknown.
_TYPE_PRICE_HINTS: dict[str, int] = {
    "fine_dining_restaurant": 3,
    "steak_house": 3,
    "wine_bar": 3,
    "night_club": 3,
    "pub": 2,
    "bar_and_grill": 2,
    "buffet_restaurant": 2,
    "fast_food_restaurant": 1,
    "food_court": 1,
    "dessert_shop": 1,
    "ice_cream_shop": 1,
    "tea_house": 1,
}

# Name tokens that reliably signal price in Indian cities. Word-boundary
# matches only; precision over recall (a wrong ₹ band is worse than none).
_NAME_CHEAP_RE = re.compile(
    r"\b(?:dhaba|tiffins?|mess|bandi|canteen|chaat|darshini|udupi)\b",
    re.IGNORECASE,
)
_NAME_PRICEY_RE = re.compile(
    r"\b(?:fine\s+din(?:e|ing)|sky\s?bar|lounge|brewery|brewhouse|brewworks|gastropub)\b",
    re.IGNORECASE,
)


class PriceSignal(NamedTuple):
    level: int | None
    source: str


def level_from_range_inr(start_inr: int | None, end_inr: int | None) -> int | None:
    """Derive a 0-4 price level from a per-person INR range."""
    if start_inr is None and end_inr is None:
        return None
    lo = start_inr if start_inr is not None else end_inr
    hi = end_inr if end_inr is not None else start_inr
    assert lo is not None and hi is not None
    mid = (lo + hi) / 2
    if mid <= 0:
        return 0
    for threshold, level in _RANGE_LEVEL_THRESHOLDS_INR:
        if mid < threshold:
            return level
    return 4


def _heuristic_level(name: str, types: list[str] | None) -> int | None:
    place_types = {t.casefold() for t in (types or [])}
    for hint_type, level in _TYPE_PRICE_HINTS.items():
        if hint_type in place_types:
            return level
    if _NAME_CHEAP_RE.search(name):
        return 1
    if _NAME_PRICEY_RE.search(name):
        return 3
    return None


def price_signal(place: PlaceItem) -> PriceSignal:
    """The place's best available price level and where it came from."""
    if place.price_level is not None:
        return PriceSignal(max(0, min(4, place.price_level)), PRICE_SOURCE_GOOGLE_LEVEL)

    range_level = level_from_range_inr(place.price_range_start_inr, place.price_range_end_inr)
    if range_level is not None:
        return PriceSignal(range_level, PRICE_SOURCE_GOOGLE_RANGE)

    heuristic = _heuristic_level(place.name, place.types)
    if heuristic is not None:
        return PriceSignal(heuristic, PRICE_SOURCE_HEURISTIC)

    return PriceSignal(None, PRICE_SOURCE_UNKNOWN)


class CostBand(NamedTuple):
    min_inr: int
    max_inr: int
    source: str


def estimate_cost_band(place: PlaceItem) -> CostBand | None:
    """Per-person INR spend estimate for display. None when there's no signal."""
    if place.price_range_start_inr is not None or place.price_range_end_inr is not None:
        lo = place.price_range_start_inr
        hi = place.price_range_end_inr
        lo = lo if lo is not None else hi
        hi = hi if hi is not None else lo
        assert lo is not None and hi is not None
        return CostBand(lo, hi, PRICE_SOURCE_GOOGLE_RANGE)

    signal = price_signal(place)
    if signal.level is None:
        return None
    band = PRICE_LEVEL_BANDS_INR[signal.level]
    return CostBand(band[0], band[1], signal.source)
