from models import PlaceItem
from price_inference import (
    PRICE_LEVEL_BANDS_INR,
    PRICE_SOURCE_GOOGLE_LEVEL,
    PRICE_SOURCE_GOOGLE_RANGE,
    PRICE_SOURCE_HEURISTIC,
    PRICE_SOURCE_UNKNOWN,
    estimate_cost_band,
    level_from_range_inr,
    price_signal,
)
from services.google_places import GooglePlacesProvider


def _place(
    name: str = "Test Place",
    *,
    types: list[str] | None = None,
    price_level: int | None = None,
    range_start: int | None = None,
    range_end: int | None = None,
) -> PlaceItem:
    return PlaceItem(
        name=name,
        address="Test Road",
        lat=0.0,
        lng=0.0,
        distance_meters=0,
        rating=4.4,
        user_ratings_total=300,
        price_level=price_level,
        price_range_start_inr=range_start,
        price_range_end_inr=range_end,
        types=types or ["restaurant"],
        provider_id="test",
    )


# ── level_from_range_inr ──────────────────────────────────────────────────────

def test_range_to_level_bands() -> None:
    assert level_from_range_inr(100, 300) == 1
    assert level_from_range_inr(400, 800) == 2
    assert level_from_range_inr(1000, 1500) == 3
    assert level_from_range_inr(2000, 4000) == 4
    assert level_from_range_inr(0, 0) == 0
    assert level_from_range_inr(None, None) is None


def test_range_to_level_handles_open_ended_ranges() -> None:
    assert level_from_range_inr(200, None) == 1
    assert level_from_range_inr(None, 2500) == 4


# ── price_signal resolution order ─────────────────────────────────────────────

def test_explicit_price_level_wins_over_range_and_heuristics() -> None:
    place = _place("Fancy Dhaba", price_level=3, range_start=100, range_end=200)
    assert price_signal(place) == (3, PRICE_SOURCE_GOOGLE_LEVEL)


def test_price_range_wins_over_heuristics() -> None:
    place = _place("Sky Lounge", range_start=150, range_end=300)
    assert price_signal(place) == (1, PRICE_SOURCE_GOOGLE_RANGE)


def test_heuristic_from_name_cheap_and_pricey() -> None:
    assert price_signal(_place("Highway Dhaba")) == (1, PRICE_SOURCE_HEURISTIC)
    assert price_signal(_place("Aqua Sky Lounge")) == (3, PRICE_SOURCE_HEURISTIC)


def test_heuristic_from_types() -> None:
    fine = _place("Some Place", types=["fine_dining_restaurant", "restaurant"])
    fast = _place("Some Place", types=["fast_food_restaurant", "restaurant"])
    assert price_signal(fine) == (3, PRICE_SOURCE_HEURISTIC)
    assert price_signal(fast) == (1, PRICE_SOURCE_HEURISTIC)


def test_no_signal_is_unknown() -> None:
    assert price_signal(_place("Plain Restaurant")) == (None, PRICE_SOURCE_UNKNOWN)


def test_heuristic_does_not_fire_on_substrings() -> None:
    # "Dhabaleshwar" contains "dhaba" only as a prefix, not a word.
    assert price_signal(_place("Dhabaleshwar Foods")).source == PRICE_SOURCE_UNKNOWN


# ── estimate_cost_band ────────────────────────────────────────────────────────

def test_estimate_prefers_real_inr_range() -> None:
    place = _place("Cafe", price_level=2, range_start=450, range_end=700)
    band = estimate_cost_band(place)
    assert band is not None
    assert (band.min_inr, band.max_inr, band.source) == (450, 700, PRICE_SOURCE_GOOGLE_RANGE)


def test_estimate_falls_back_to_level_band() -> None:
    band = estimate_cost_band(_place("Cafe", price_level=2))
    assert band is not None
    assert (band.min_inr, band.max_inr) == PRICE_LEVEL_BANDS_INR[2]
    assert band.source == PRICE_SOURCE_GOOGLE_LEVEL


def test_estimate_from_heuristic_is_marked_as_such() -> None:
    band = estimate_cost_band(_place("Highway Dhaba"))
    assert band is not None
    assert band.source == PRICE_SOURCE_HEURISTIC
    assert (band.min_inr, band.max_inr) == PRICE_LEVEL_BANDS_INR[1]


def test_estimate_none_without_signal() -> None:
    assert estimate_cost_band(_place("Plain Restaurant")) is None


# ── Places API (New) response parsing ─────────────────────────────────────────

def test_raw_from_new_place_parses_price_fields() -> None:
    item = {
        "id": "ChIJtest",
        "displayName": {"text": "Biryani Corner", "languageCode": "en"},
        "formattedAddress": "Road No 1, Hyderabad",
        "location": {"latitude": 17.4, "longitude": 78.5},
        "rating": 4.5,
        "userRatingCount": 1200,
        "types": ["restaurant", "food"],
        "businessStatus": "OPERATIONAL",
        "priceLevel": "PRICE_LEVEL_MODERATE",
        "priceRange": {
            "startPrice": {"currencyCode": "INR", "units": "400"},
            "endPrice": {"currencyCode": "INR", "units": "800"},
        },
    }

    raw = GooglePlacesProvider._raw_from_new_place(item)

    assert raw.provider_id == "ChIJtest"
    assert raw.name == "Biryani Corner"
    assert raw.address == "Road No 1, Hyderabad"
    assert (raw.lat, raw.lng) == (17.4, 78.5)
    assert raw.rating == 4.5
    assert raw.user_ratings_total == 1200
    assert raw.business_status == "OPERATIONAL"
    assert raw.price_level == 2
    assert raw.price_range_start_inr == 400
    assert raw.price_range_end_inr == 800


def test_raw_from_new_place_tolerates_missing_fields() -> None:
    raw = GooglePlacesProvider._raw_from_new_place({"id": "x"})

    assert raw.provider_id == "x"
    assert raw.rating is None
    assert raw.price_level is None
    assert raw.price_range_start_inr is None
    assert raw.price_range_end_inr is None


def test_raw_from_new_place_ignores_non_inr_price_range() -> None:
    item = {
        "id": "x",
        "priceRange": {
            "startPrice": {"currencyCode": "USD", "units": "10"},
            "endPrice": {"currencyCode": "USD", "units": "20"},
        },
        "priceLevel": "PRICE_LEVEL_UNSPECIFIED",
    }

    raw = GooglePlacesProvider._raw_from_new_place(item)

    assert raw.price_level is None
    assert raw.price_range_start_inr is None
    assert raw.price_range_end_inr is None
