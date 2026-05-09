"""
Stop-sequence templates keyed by Occasion.

Each TemplateStop carries:
  category        – our internal StopCategory label (drives dwell time)
  places_types    – ordered tuple of Google Places (legacy) `type` values to try.
                    The generator tries each in order and uses the first that
                    returns results. This makes the pipeline resilient to
                    sparse cities where only some categories have venues.

All values in places_types must be in ALLOWED_NEARBY_TYPES (models.py).
"""

from dataclasses import dataclass

from models import Occasion, StopCategory


@dataclass(frozen=True)
class TemplateStop:
    category: StopCategory
    # Ordered fallback list of Google Places legacy `type` values.
    # The first that returns places wins; later entries broaden the search.
    places_types: tuple[str, ...]


TEMPLATES: dict[Occasion, list[TemplateStop]] = {
    Occasion.date: [
        TemplateStop(
            category=StopCategory.restaurant,
            places_types=("restaurant", "cafe"),
        ),
        TemplateStop(
            category=StopCategory.other,
            places_types=("bakery", "cafe"),
        ),
        TemplateStop(
            category=StopCategory.attraction,
            places_types=("tourist_attraction", "park", "art_gallery", "museum"),
        ),
    ],
    Occasion.friends: [
        TemplateStop(
            category=StopCategory.bar,
            places_types=("bar", "night_club", "restaurant"),
        ),
        TemplateStop(
            category=StopCategory.activity,
            places_types=(
                "bowling_alley",
                "movie_theater",
                "amusement_park",
                "shopping_mall",
                "tourist_attraction",
            ),
        ),
        TemplateStop(
            category=StopCategory.restaurant,
            places_types=("meal_takeaway", "restaurant", "cafe"),
        ),
    ],
    Occasion.solo: [
        TemplateStop(
            category=StopCategory.cafe,
            places_types=("cafe", "bakery"),
        ),
        TemplateStop(
            category=StopCategory.other,
            places_types=("book_store", "library", "park", "art_gallery"),
        ),
        TemplateStop(
            category=StopCategory.attraction,
            places_types=("tourist_attraction", "museum", "park"),
        ),
    ],
    Occasion.family: [
        TemplateStop(
            category=StopCategory.restaurant,
            places_types=("restaurant", "cafe"),
        ),
        TemplateStop(
            category=StopCategory.activity,
            places_types=(
                "park",
                "zoo",
                "aquarium",
                "amusement_park",
                "museum",
                "tourist_attraction",
            ),
        ),
        TemplateStop(
            category=StopCategory.other,
            places_types=("bakery", "cafe", "shopping_mall"),
        ),
    ],
}
