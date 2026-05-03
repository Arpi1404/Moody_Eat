"""
Stop-sequence templates keyed by Occasion.

Each TemplateStop carries:
  category        – our internal StopCategory label
  places_type     – the Google Places (legacy) type string to pass to the
                    nearby-search API, or None where no mapping exists in
                    ALLOWED_NEARBY_TYPES
  places_gap      – human-readable note when the mapping is absent or
                    approximate; None means the mapping is clean

ALLOWED_NEARBY_TYPES (from models.py) for reference:
  restaurant, cafe, bar, bakery, meal_takeaway, meal_delivery

Gaps to resolve before wiring templates into live search:
  - dessert / dessert_or_ice_cream  → no "dessert_shop" type; mapped to
      "bakery" as closest available, but ice-cream shops and patisseries
      are not bakeries.  Consider expanding ALLOWED_NEARBY_TYPES with
      "ice_cream_shop" (supported by Places API New).
  - scenic_walk_or_view             → no walkable-landmark type in our
      allowed set.  Full Places API supports "tourist_attraction" and
      "natural_feature"; add one to ALLOWED_NEARBY_TYPES or handle as a
      special non-search stop (user-supplied or geocoded point of interest).
  - activity_venue                  → no match.  Full Places API has
      "amusement_park", "bowling_alley", "movie_theater", etc.  Needs a
      new StopCategory value and an expansion of ALLOWED_NEARBY_TYPES.
  - late_night_food                 → approximated as "meal_takeaway";
      hour-of-day filtering is not yet supported by the nearby-search layer.
  - bookstore_or_park               → neither type is in ALLOWED_NEARBY_TYPES.
      "book_store" exists in Places API New; "park" maps to "tourist_attraction"
      or the new place type "park".  Add both to ALLOWED_NEARBY_TYPES.
  - park_or_play_area               → same as above; "playground" is a Places
      API New type not yet in our allowed set.
"""

from dataclasses import dataclass

from models import Occasion, StopCategory


@dataclass(frozen=True)
class TemplateStop:
    category: StopCategory
    # Google Places legacy type for nearby search; None = no clean mapping yet
    places_type: str | None
    # Non-None when the mapping is missing or only approximate
    places_gap: str | None = None


TEMPLATES: dict[Occasion, list[TemplateStop]] = {
    Occasion.date: [
        TemplateStop(
            category=StopCategory.restaurant,
            places_type="restaurant",
        ),
        TemplateStop(
            category=StopCategory.other,
            places_type="bakery",  # closest available; see module docstring
            places_gap=(
                "No 'dessert_shop' in ALLOWED_NEARBY_TYPES. "
                "Using 'bakery' as fallback. "
                "Consider adding 'ice_cream_shop' (Places API New)."
            ),
        ),
        TemplateStop(
            category=StopCategory.attraction,
            places_type=None,
            places_gap=(
                "No walkable-landmark type in ALLOWED_NEARBY_TYPES. "
                "Candidates: 'tourist_attraction' or 'natural_feature' "
                "(Places API New). Alternatively, treat as a non-search stop."
            ),
        ),
    ],
    Occasion.friends: [
        TemplateStop(
            category=StopCategory.bar,
            places_type="bar",
            # "bar_or_restaurant" — bar is the primary intent for an evening
            # outing; fall back to restaurant at the call site if bar returns
            # no results.
        ),
        TemplateStop(
            category=StopCategory.activity,
            places_type=None,
            places_gap=(
                "No activity-venue type in ALLOWED_NEARBY_TYPES. "
                "Full Places API has 'bowling_alley', 'movie_theater', "
                "'amusement_park'. Expand ALLOWED_NEARBY_TYPES and add a "
                "corresponding StopCategory value."
            ),
        ),
        TemplateStop(
            category=StopCategory.restaurant,
            places_type="meal_takeaway",
            places_gap=(
                "Late-night food approximated as 'meal_takeaway'. "
                "Hour-of-day filtering is not yet supported by the "
                "nearby-search layer; any open result will be returned."
            ),
        ),
    ],
    Occasion.solo: [
        TemplateStop(
            category=StopCategory.cafe,
            places_type="cafe",
        ),
        TemplateStop(
            category=StopCategory.other,
            places_type=None,
            places_gap=(
                "Neither 'book_store' nor 'park' is in ALLOWED_NEARBY_TYPES. "
                "'book_store' is a Places API New type; 'park' maps to "
                "'tourist_attraction' or the new 'park' type. "
                "Add both to ALLOWED_NEARBY_TYPES."
            ),
        ),
    ],
    Occasion.family: [
        TemplateStop(
            category=StopCategory.restaurant,
            places_type="restaurant",
            # Google Places has no 'family_restaurant' type; plain 'restaurant'
            # is the closest. Caller can layer keyword hints (e.g. "family
            # friendly") via the text-search path if needed.
        ),
        TemplateStop(
            category=StopCategory.other,
            places_type="bakery",  # closest available; see module docstring
            places_gap=(
                "No 'ice_cream_shop' or 'dessert_shop' in ALLOWED_NEARBY_TYPES. "
                "Using 'bakery' as fallback. "
                "Consider adding 'ice_cream_shop' (Places API New)."
            ),
        ),
        TemplateStop(
            category=StopCategory.attraction,
            places_type=None,
            places_gap=(
                "Neither 'park' nor 'playground' is in ALLOWED_NEARBY_TYPES. "
                "Both exist as Places API New types. "
                "Add to ALLOWED_NEARBY_TYPES alongside a new StopCategory value."
            ),
        ),
    ],
}
