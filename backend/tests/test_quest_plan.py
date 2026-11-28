"""What a quest is made of and in what order: one meal per plan, stops ordered
by the time of day, places matched on Google's primary type, the popularity
cap, the walking threshold, and the titles and fallback text."""

import asyncio
import re
from datetime import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from deps import get_nearby_places_service
from main import app
from models import (
    CostEstimate,
    DayPart,
    Occasion,
    PlaceItem,
    Quest,
    QuestGenerationRequest,
    Stop,
    StopCategory,
    TravelMode,
)
from quest_generator import (
    _DAY_PART_START,
    _DRIVE_M_PER_MIN,
    _FIRST_STOP_NEAR_M,
    _STRONG_RATING_FLOOR,
    _STRONG_RATINGS_TOTAL_FLOOR,
    _TITLES,
    _WALK_M_PER_MIN,
    _WALK_THRESHOLD_M,
    _first_stop_fit,
    _is_strong,
    _mood_reject_rule,
    _pick,
    _popularity_cap,
    _quest_title,
    _travel_time,
    _why,
    assemble_quest,
)
from quest_templates import (
    AFTER_MEAL_FOOD_ROLES,
    CAFE_FAMILY,
    DESSERT_FAMILY,
    DINNER_FAMILY,
    DRINKS_FAMILY,
    FOOD_ROLES,
    MAX_STOPS,
    MEAL_FAMILY,
    PLANS,
    SIGHT_FAMILY,
)
from services.google_places import _NEARBY_FIELD_MASK_NEW, GooglePlacesProvider
from services.nearby_places_service import NearbyPlacesService
from services.place_blurbs_service import (
    _BUDGET_WORDS,
    _OUTING_PHRASES,
    _fallback_narrative,
)
from services.places_provider import PlaceHours, RawPlace, ResolvedLocation

OPEN_ALL_DAY = PlaceHours(None, None, True)
HOURS_UNKNOWN = PlaceHours(None, None, False)
FRONTEND_SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"


def _raw(
    provider_id: str,
    name: str,
    primary: str | None,
    *,
    tags: tuple[str, ...] = (),
    lat: float = 0.001,
    rating: float = 4.5,
    reviews: int = 600,
    price_level: int | None = None,
) -> RawPlace:
    """A place as the provider returns it: `primary` is its primary type, and
    its tags are that plus `tags`."""
    types = ([primary] if primary else []) + list(tags)
    return RawPlace(
        provider_id, name, "Road", lat, 0.0, rating, types, reviews,
        price_level=price_level, primary_type=primary,
    )


class PoolProvider:
    """Places by searched type. Everything is open all day unless `hours` says
    otherwise for a place."""

    def __init__(
        self,
        pools: dict[str, list[RawPlace]],
        hours: dict[str, PlaceHours] | None = None,
    ) -> None:
        self.pools = pools
        self.hours = hours or {}
        self.searches: list[tuple[str, int]] = []
        self.hours_requested: list[str] = []

    async def geocode(self, query: str) -> ResolvedLocation:
        return ResolvedLocation(name=query, lat=0.0, lng=0.0)

    async def nearby_by_type(
        self,
        *,
        lat: float,
        lng: float,
        radius_meters: int,
        place_type: str,
        target_count: int | None = None,
    ) -> list[RawPlace]:
        self.searches.append((place_type, radius_meters))
        return list(self.pools.get(place_type, []))

    async def place_hours(self, *, provider_id: str, weekday: int) -> PlaceHours:
        self.hours_requested.append(provider_id)
        return self.hours.get(provider_id, OPEN_ALL_DAY)


def _city() -> dict[str, list[RawPlace]]:
    """One good place of each kind, a short walk apart."""
    return {
        "park": [_raw("park", "Lake Park", "park", lat=0.0010, reviews=5000)],
        "cafe": [_raw("cafe", "Corner Coffee", "cafe", lat=0.0015)],
        "restaurant": [
            _raw("bistro", "Garden Bistro", "italian_restaurant", tags=("restaurant",), lat=0.0020),
        ],
        "bakery": [
            _raw("patisserie", "Sweet Patisserie", "bakery", tags=("cafe",), lat=0.0025),
        ],
        "tourist_attraction": [
            _raw("fort", "Old Fort", "historical_landmark", tags=("tourist_attraction",),
                 lat=0.0030, rating=4.6, reviews=2000),
        ],
        "art_gallery": [_raw("gallery", "City Gallery", "art_gallery", lat=0.0035)],
        "bar": [_raw("pub", "Corner Pub", "pub", tags=("bar",), lat=0.0040)],
        "bowling_alley": [_raw("lanes", "Strike Lanes", "bowling_alley", lat=0.0045)],
    }


@pytest.fixture
def fake_narrative(monkeypatch) -> list[dict]:
    calls: list[dict] = []

    async def _narrative(**kwargs) -> str:
        calls.append(kwargs)
        return "A test quest."

    monkeypatch.setattr("quest_generator.generate_quest_narrative", _narrative)
    return calls


def _request(
    occasion: Occasion,
    day_part: DayPart | None,
    stop_count: int | None,
    *,
    cost: CostEstimate = CostEstimate.mid,
    **extra,
) -> QuestGenerationRequest:
    return QuestGenerationRequest(
        location="Govindpuram",
        occasion=occasion,
        cost_estimate=cost,
        people=2,
        stop_count=stop_count,
        day_part=day_part,
        **extra,
    )


def _quest(provider: PoolProvider, req: QuestGenerationRequest) -> Quest:
    return asyncio.run(assemble_quest(req, NearbyPlacesService(provider)))


def _names(quest: Quest) -> list[str]:
    return [stop.place.name for stop in quest.stops]


def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute


# ── One sit-down meal per plan ────────────────────────────────────────────────

def test_every_plan_has_one_meal_at_most_and_only_dessert_or_drinks_after_it() -> None:
    for occasion in Occasion:
        for day_part in DayPart:
            plan = PLANS[occasion][day_part]
            # Every plan holds four stops, except a family night (see
            # test_only_a_family_night_is_shorter).
            assert len(plan.sequence) == (
                3 if (occasion, day_part) == (Occasion.family, DayPart.night) else MAX_STOPS
            )
            assert sorted(map(id, plan.keep)) == sorted(map(id, plan.sequence))
            for count in range(1, MAX_STOPS + 1):
                stops = plan.stops(count)
                assert len(stops) == min(count, len(plan.sequence))
                # The worst a sparse area can do: every spare is called on,
                # each added at the end.
                for order in (stops, stops + plan.spares(count)):
                    roles = [stop.role for stop in order]
                    where = f"{occasion.value}/{day_part.value}/{count}: {roles}"
                    assert roles.count("meal") <= 1, where
                    if "meal" in roles:
                        after = roles[roles.index("meal") + 1:]
                        food_after = [r for r in after if r in FOOD_ROLES]
                        assert set(food_after) <= AFTER_MEAL_FOOD_ROLES, where


def test_four_stop_date_is_one_meal_not_a_run_of_food_stops(fake_narrative) -> None:
    """It used to be restaurant, bakery, cafe, attraction."""
    night = _quest(PoolProvider(_city()), _request(Occasion.date, DayPart.night, 4))
    evening = _quest(PoolProvider(_city()), _request(Occasion.date, DayPart.evening, 4))

    assert _names(night) == ["Garden Bistro", "Sweet Patisserie", "Strike Lanes", "Corner Pub"]
    assert _names(evening) == ["Lake Park", "Corner Coffee", "Garden Bistro", "Sweet Patisserie"]
    for quest in (night, evening):
        categories = [stop.category for stop in quest.stops]
        assert categories.count(StopCategory.restaurant) == 1


def test_friends_night_is_one_dinner_then_play_then_drinks(fake_narrative) -> None:
    """It used to be a bar and grill, bowling, then a buffet at ten to ten."""
    quest = _quest(PoolProvider(_city()), _request(Occasion.friends, DayPart.night, 3))

    assert _names(quest) == ["Garden Bistro", "Strike Lanes", "Corner Pub"]
    assert quest.stops[0].time_block_start == time(20, 0)


# ── Ordered by the time of day ────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("occasion", "day_part", "count", "expected"),
    [
        # Morning: outdoors first, then breakfast or coffee.
        (Occasion.date, DayPart.morning, 2, ["Lake Park", "Corner Coffee"]),
        (Occasion.solo, DayPart.morning, 3, ["Lake Park", "Corner Coffee", "City Gallery"]),
        (Occasion.friends, DayPart.morning, 3, ["Lake Park", "Corner Coffee", "Strike Lanes"]),
        (Occasion.family, DayPart.morning, 3, ["Lake Park", "Garden Bistro", "Sweet Patisserie"]),
        # Afternoon: lunch first.
        (Occasion.date, DayPart.afternoon, 3, ["Garden Bistro", "Sweet Patisserie", "Old Fort"]),
        # No park at 14:00 (the midday heat): the sight instead.
        (Occasion.family, DayPart.afternoon, 3, ["Garden Bistro", "Old Fort", "Sweet Patisserie"]),
        (Occasion.friends, DayPart.afternoon, 3, ["Garden Bistro", "Strike Lanes", "Corner Pub"]),
        # Evening: something to do, a walk or a coffee first; dinner after.
        (Occasion.date, DayPart.evening, 3, ["Lake Park", "Corner Coffee", "Garden Bistro"]),
        (Occasion.friends, DayPart.evening, 3, ["Strike Lanes", "Garden Bistro", "Corner Pub"]),
        (Occasion.family, DayPart.evening, 3, ["Lake Park", "Garden Bistro", "Sweet Patisserie"]),
        (Occasion.solo, DayPart.evening, 3, ["Lake Park", "City Gallery", "Corner Coffee"]),
        # Night: dinner first, then dessert or drinks.
        (Occasion.date, DayPart.night, 3, ["Garden Bistro", "Sweet Patisserie", "Corner Pub"]),
        (Occasion.friends, DayPart.night, 2, ["Garden Bistro", "Corner Pub"]),
        (Occasion.family, DayPart.night, 2, ["Garden Bistro", "Sweet Patisserie"]),
    ],
)
def test_stops_are_ordered_by_the_time_of_day(
    fake_narrative, occasion, day_part, count, expected
) -> None:
    quest = _quest(PoolProvider(_city()), _request(occasion, day_part, count))

    assert _names(quest) == expected
    hour, minute = _DAY_PART_START[day_part]
    assert quest.stops[0].time_block_start == time(hour, minute)


def test_one_stop_is_whatever_suits_the_hour(fake_narrative) -> None:
    def one(occasion: Occasion, day_part: DayPart) -> str:
        quest = _quest(PoolProvider(_city()), _request(occasion, day_part, 1))
        return quest.stops[0].place.name

    # A one-stop date is dinner, in the evening as at night.
    assert one(Occasion.date, DayPart.evening) == "Garden Bistro"
    assert one(Occasion.date, DayPart.night) == "Garden Bistro"
    assert one(Occasion.date, DayPart.afternoon) == "Garden Bistro"
    # Friends in the morning are not sent to a bar.
    assert one(Occasion.friends, DayPart.morning) == "Corner Coffee"
    assert one(Occasion.friends, DayPart.night) == "Corner Pub"


@pytest.mark.parametrize(
    ("occasion", "count", "expected", "starts"),
    [
        # Dinner anchors a short evening date and a one-stop family evening,
        # and the plan starts at dinner time rather than at 17:30.
        (Occasion.date, 1, ["Garden Bistro"], time(19, 0)),
        (Occasion.date, 2, ["Garden Bistro", "Sweet Patisserie"], time(19, 0)),
        (Occasion.family, 1, ["Garden Bistro"], time(19, 0)),
        # Longer ones keep their shape and start: something first, then dinner.
        (Occasion.date, 3, ["Lake Park", "Corner Coffee", "Garden Bistro"], time(17, 30)),
        (Occasion.family, 2, ["Lake Park", "Garden Bistro"], time(17, 30)),
        # Friends are unchanged: one evening stop is a bar, at 17:30.
        (Occasion.friends, 1, ["Corner Pub"], time(17, 30)),
    ],
)
def test_short_evening_plans_are_dinner_led(
    fake_narrative, occasion, count, expected, starts
) -> None:
    quest = _quest(PoolProvider(_city()), _request(occasion, DayPart.evening, count))

    assert _names(quest) == expected
    assert quest.stops[0].time_block_start == starts
    # Still an evening quest by name, whatever time dinner starts.
    assert fake_narrative[-1]["day_part"] == "evening"


def test_dinner_led_evening_date_is_titled_for_the_evening(fake_narrative) -> None:
    quest = _quest(PoolProvider(_city()), _request(Occasion.date, DayPart.evening, 1))

    assert quest.title == "An Evening Date in Govindpuram"
    assert quest.stops[0].time_block_start == time(19, 0)


def test_one_stop_family_morning_is_lunch_at_noon(fake_narrative) -> None:
    """The same rule in the morning: a plan that opens with the meal starts at
    the meal hour."""
    quest = _quest(PoolProvider(_city()), _request(Occasion.family, DayPart.morning, 1))

    assert _names(quest) == ["Garden Bistro"]
    assert quest.stops[0].time_block_start == time(12, 0)


def test_dinner_led_start_waits_for_a_kitchen_that_opens_at_seven(fake_narrative) -> None:
    """The reason for the 19:00 start: at 17:30 this kitchen is shut and the
    only dinner on offer would be an all-day place."""
    provider = PoolProvider(
        {
            "restaurant": [
                _raw("bistro", "Garden Bistro", "italian_restaurant", tags=("restaurant",),
                     rating=4.7, reviews=3_000),
                _raw("allday", "All Day Diner", "american_restaurant", tags=("restaurant",),
                     rating=4.1, reviews=3_000),
            ],
        },
        hours={"bistro": PlaceHours("19:00", "23:30", False)},
    )

    quest = _quest(provider, _request(Occasion.date, DayPart.evening, 1))

    assert _names(quest) == ["Garden Bistro"]
    assert quest.stops[0].time_block_start == time(19, 0)


def test_day_part_start_times_are_unchanged() -> None:
    assert _DAY_PART_START == {
        DayPart.morning: (10, 0),
        DayPart.afternoon: (13, 0),
        DayPart.evening: (17, 30),
        DayPart.night: (20, 0),
    }


def test_evening_dinner_is_held_until_seven_and_the_plan_has_no_gap(fake_narrative) -> None:
    quest = _quest(PoolProvider(_city()), _request(Occasion.date, DayPart.evening, 3))

    walk, coffee, dinner = quest.stops
    assert walk.time_block_start == time(17, 30)
    assert dinner.category == StopCategory.restaurant
    assert dinner.time_block_start == time(19, 0)
    # The wait is spent over coffee, which runs past its usual 40 minutes...
    coffee_minutes = _minutes(coffee.time_block_end) - _minutes(coffee.time_block_start)
    assert 40 < coffee_minutes <= 70
    # ...so every stop still starts when the one before ends, plus the trip.
    for before, after in zip(quest.stops, quest.stops[1:]):
        assert _minutes(after.time_block_start) == (
            _minutes(before.time_block_end) + before.travel_to_next_minutes
        )
    assert quest.total_duration_minutes == 150


def test_the_wait_for_dinner_is_capped_at_half_an_hour(fake_narrative) -> None:
    """With only a coffee before it, dinner cannot reach seven: the coffee
    runs 30 minutes longer and dinner starts when it ends."""
    city = _city()
    provider = PoolProvider({"cafe": city["cafe"], "restaurant": city["restaurant"]})

    quest = _quest(provider, _request(Occasion.date, DayPart.evening, 3))

    coffee, dinner = quest.stops
    assert (coffee.time_block_start, coffee.time_block_end) == (time(17, 30), time(18, 40))
    assert dinner.time_block_start == time(18, 41)


def test_the_wait_for_dinner_never_outlasts_the_stop_before_it(fake_narrative) -> None:
    city = _city()
    provider = PoolProvider(
        {"cafe": city["cafe"], "restaurant": city["restaurant"]},
        hours={"cafe": PlaceHours("08:00", "18:15", False)},
    )

    quest = _quest(provider, _request(Occasion.date, DayPart.evening, 3))

    coffee, dinner = quest.stops
    # The cafe shuts at 18:15, so that is as long as anyone can stay.
    assert coffee.time_block_end == time(18, 15)
    assert dinner.time_block_start == time(18, 16)


def test_dinner_alone_in_the_evening_starts_at_the_start_time(fake_narrative) -> None:
    """Nothing comes before it, so there is nowhere to wait: as before."""
    provider = PoolProvider({"restaurant": _city()["restaurant"]})

    quest = _quest(provider, _request(Occasion.date, DayPart.evening, 3))

    assert _names(quest) == ["Garden Bistro"]
    assert quest.stops[0].time_block_start == time(17, 30)


def test_morning_lunch_waits_for_noon(fake_narrative) -> None:
    quest = _quest(PoolProvider(_city()), _request(Occasion.family, DayPart.morning, 2))

    park, lunch = quest.stops
    assert _names(quest) == ["Lake Park", "Garden Bistro"]
    # An hour in the park would end at 11:00; a park can stretch by an hour,
    # so lunch starts at noon.
    assert park.time_block_end == time(11, 59)
    assert lunch.time_block_start == time(12, 0)


def test_request_without_a_day_part_keeps_the_occasions_own_time_and_order(
    fake_narrative,
) -> None:
    date = _quest(PoolProvider(_city()), _request(Occasion.date, None, 3))
    solo = _quest(PoolProvider(_city()), _request(Occasion.solo, None, 3))

    # A date with no day part starts at 19:00, which is dinner time already.
    assert date.stops[0].time_block_start == time(19, 0)
    assert _names(date) == ["Garden Bistro", "Sweet Patisserie", "Corner Pub"]
    assert date.title == "An Evening Date in Govindpuram"
    assert solo.stops[0].time_block_start == time(10, 0)
    assert _names(solo) == ["Lake Park", "Corner Coffee", "City Gallery"]


def test_request_without_a_stop_count_plans_two_stops(fake_narrative) -> None:
    quest = _quest(PoolProvider(_city()), _request(Occasion.date, None, None))

    assert len(quest.stops) == 2
    assert _names(quest) == ["Garden Bistro", "Sweet Patisserie"]


# ── Matching on Google's primary type ─────────────────────────────────────────

def test_primary_type_is_requested_and_carried_to_the_place() -> None:
    raw = GooglePlacesProvider._raw_from_new_place({
        "id": "ChIJpizza",
        "displayName": {"text": "Slice House"},
        "location": {"latitude": 1.0, "longitude": 2.0},
        "types": ["pizza_restaurant", "bar", "restaurant"],
        "primaryType": "pizza_restaurant",
    })
    untyped = GooglePlacesProvider._raw_from_new_place({
        "id": "ChIJnone", "displayName": {"text": "Somewhere"}, "types": ["bar"],
    })
    legacy = GooglePlacesProvider._raw_from_nearby_item({
        "place_id": "ChIJlegacy", "name": "Old Bar", "types": ["bar"],
        "geometry": {"location": {"lat": 1.0, "lng": 2.0}},
    })

    assert raw.primary_type == "pizza_restaurant"
    assert untyped.primary_type is None
    assert legacy.primary_type is None


def test_nearby_field_mask_is_exactly_these_fields() -> None:
    """Every field is billed. primaryType and utcOffsetMinutes are in the same
    tier as types; hours, phone and website in the Enterprise tier the rating
    and price fields already put this request in. Nothing here may come from
    Enterprise + Atmosphere, and anything added should be added on purpose."""
    assert set(_NEARBY_FIELD_MASK_NEW.split(",")) == {
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.rating",
        "places.userRatingCount",
        "places.types",
        "places.primaryType",
        "places.businessStatus",
        "places.priceLevel",
        "places.priceRange",
        # Enterprise, like rating and price: the same SKU, no dearer.
        "places.regularOpeningHours.periods",
        "places.internationalPhoneNumber",
        "places.websiteUri",
        # Pro.
        "places.utcOffsetMinutes",
    }


def test_type_families_judge_a_place_by_its_primary_type() -> None:
    # Any cuisine is a restaurant; fast food and dessert parlours are not a
    # sit-down meal, and neither is a bar or a cafe.
    assert MEAL_FAMILY.accepts("south_indian_restaurant", ["restaurant"])
    assert MEAL_FAMILY.accepts("restaurant", [])
    assert MEAL_FAMILY.accepts("bistro", [])
    assert not MEAL_FAMILY.accepts("fast_food_restaurant", ["restaurant"])
    assert not MEAL_FAMILY.accepts("dessert_restaurant", ["restaurant"])
    assert not MEAL_FAMILY.accepts("brewpub", ["restaurant"])
    assert not MEAL_FAMILY.accepts("cafe", ["restaurant"])
    assert not MEAL_FAMILY.accepts("food_court", ["restaurant"])
    # Breakfast places are lunch, not dinner.
    assert MEAL_FAMILY.accepts("breakfast_restaurant", [])
    assert not DINNER_FAMILY.accepts("breakfast_restaurant", [])
    assert DINNER_FAMILY.accepts("north_indian_restaurant", [])

    assert DRINKS_FAMILY.accepts("brewpub", ["bar"])
    assert DRINKS_FAMILY.accepts("cocktail_bar", [])
    assert not DRINKS_FAMILY.accepts("pizza_restaurant", ["bar"])
    assert not DRINKS_FAMILY.accepts("south_indian_restaurant", ["bar_and_grill", "bar"])

    assert CAFE_FAMILY.accepts("coffee_shop", [])
    assert not CAFE_FAMILY.accepts("fast_food_restaurant", ["cafe"])
    assert not CAFE_FAMILY.accepts("european_restaurant", ["cafe"])

    # A bakery or cake shop counts when Google also calls it a cafe.
    assert DESSERT_FAMILY.accepts("ice_cream_shop", [])
    assert DESSERT_FAMILY.accepts("bakery", ["bakery", "cake_shop", "cafe"])
    assert not DESSERT_FAMILY.accepts("bakery", ["bakery", "food_store", "store"])
    assert not DESSERT_FAMILY.accepts("cake_shop", ["cake_shop", "dessert_shop", "bakery"])
    assert DESSERT_FAMILY.accepts("cake_shop", ["cake_shop", "coffee_shop"])
    assert not DESSERT_FAMILY.accepts("candy_store", ["bakery"])

    assert SIGHT_FAMILY.accepts("national_park", ["park"])
    assert not SIGHT_FAMILY.accepts("dog_park", ["park"])
    assert not SIGHT_FAMILY.accepts("playground", ["park"])
    assert not SIGHT_FAMILY.accepts("amusement_center", ["tourist_attraction"])

    # No primary type: nothing to judge by, so the tag is trusted as before.
    for family in (MEAL_FAMILY, DRINKS_FAMILY, CAFE_FAMILY, DESSERT_FAMILY, SIGHT_FAMILY):
        assert family.accepts(None, ["anything"])
        assert family.accepts("", [])


def test_pizzeria_tagged_bar_does_not_win_the_bar_stop(fake_narrative) -> None:
    provider = PoolProvider({
        "bar": [
            # Better rated, far more reviewed, price known: it used to win.
            _raw("pizza", "Slice House", "pizza_restaurant", tags=("bar", "restaurant"),
                 rating=4.8, reviews=9000, price_level=2),
            _raw("pub", "Corner Pub", "pub", tags=("bar",), rating=4.1, reviews=300),
        ],
    })

    quest = _quest(provider, _request(Occasion.friends, DayPart.night, 1))

    assert _names(quest) == ["Corner Pub"]
    assert quest.stops[0].place.primary_type == "pub"


def test_cake_order_shop_is_not_a_dates_dessert_stop(fake_narrative) -> None:
    provider = PoolProvider({
        "restaurant": _city()["restaurant"],
        "bakery": [
            _raw("cakes", "Two Rabbits Designer Cakes", "bakery", tags=("food_store",),
                 lat=0.0021, rating=4.9, reviews=1200, price_level=2),
            _raw("orders", "Special Cake House", "cake_shop", tags=("bakery", "dessert_shop"),
                 lat=0.0021, rating=4.8, reviews=900, price_level=2),
            _raw("patisserie", "Sweet Patisserie", "bakery", tags=("cafe",),
                 lat=0.0025, rating=4.2, reviews=400),
        ],
    })

    quest = _quest(provider, _request(Occasion.date, DayPart.night, 2))

    assert _names(quest) == ["Garden Bistro", "Sweet Patisserie"]


def test_chaat_stall_is_not_the_date_dinner(fake_narrative) -> None:
    provider = PoolProvider({
        "restaurant": [
            _raw("chaat", "Maharaja Chaat", "fast_food_restaurant", tags=("restaurant",),
                 rating=4.8, reviews=12000, price_level=2),
            _raw("bistro", "Garden Bistro", "italian_restaurant", tags=("restaurant",),
                 rating=4.2, reviews=400),
        ],
    })

    quest = _quest(provider, _request(Occasion.date, DayPart.night, 1))

    assert _names(quest) == ["Garden Bistro"]


def test_breakfast_place_is_lunch_but_not_dinner(fake_narrative) -> None:
    pools = {
        "restaurant": [
            _raw("eggs", "Sunny Side Kitchen", "breakfast_restaurant", tags=("restaurant",),
                 rating=4.8, reviews=5000, price_level=2),
            _raw("bistro", "Garden Bistro", "italian_restaurant", tags=("restaurant",),
                 rating=4.2, reviews=400),
        ],
    }

    lunch = _quest(PoolProvider(pools), _request(Occasion.date, DayPart.afternoon, 1))
    dinner = _quest(PoolProvider(pools), _request(Occasion.date, DayPart.night, 1))

    assert _names(lunch) == ["Sunny Side Kitchen"]
    assert _names(dinner) == ["Garden Bistro"]


def test_real_bar_under_a_later_type_beats_a_mistagged_first_type(fake_narrative) -> None:
    provider = PoolProvider({
        "bar": [
            _raw("pizza", "Slice House", "pizza_restaurant", tags=("bar",), rating=4.8, reviews=9000),
        ],
        "night_club": [
            _raw("club", "Late Room", "night_club", rating=4.1, reviews=300),
        ],
    })

    quest = _quest(provider, _request(Occasion.friends, DayPart.night, 1))

    assert _names(quest) == ["Late Room"]


def test_when_nothing_matches_the_tagged_place_is_still_used(fake_narrative) -> None:
    """The stop is never emptied: with no real bar anywhere in the fallback
    list, the pizzeria that carries the tag is the bar stop, as before."""
    provider = PoolProvider({
        "bar": [
            _raw("pizza", "Slice House", "pizza_restaurant", tags=("bar",), rating=4.8, reviews=9000),
        ],
    })

    quest = _quest(provider, _request(Occasion.friends, DayPart.night, 1))

    assert _names(quest) == ["Slice House"]
    # Every type in the list was tried for a real bar first.
    assert {place_type for place_type, _ in provider.searches} == {
        "bar", "night_club", "restaurant",
    }


def test_places_without_a_primary_type_are_chosen_by_tag_as_before(fake_narrative) -> None:
    """The legacy API has no primary type; nothing changes for it."""
    provider = PoolProvider({
        "bar": [
            _raw("a", "Top Scored", None, tags=("bar", "pizza_restaurant"), rating=4.8, reviews=9000),
            _raw("b", "Also Ran", None, tags=("bar",), rating=4.1, reviews=300),
        ],
    })

    quest = _quest(provider, _request(Occasion.friends, DayPart.night, 1))

    assert _names(quest) == ["Top Scored"]
    assert quest.stops[0].place.primary_type is None
    # The first type answered, so nothing further was searched or paid for.
    assert {place_type for place_type, _ in provider.searches} == {"bar"}


def test_childrens_park_is_passed_over_except_on_a_family_outing(fake_narrative) -> None:
    pools = {
        "park": [
            _raw("kids", "Defence Colony Children's Park", "park", rating=4.6, reviews=2500),
            _raw("green", "Indiranagara Park", "park", lat=0.0012, rating=4.3, reviews=1500),
        ],
    }

    solo = _quest(PoolProvider(pools), _request(Occasion.solo, DayPart.morning, 2))
    family = _quest(PoolProvider(pools), _request(Occasion.family, DayPart.evening, 1))
    only_kids = _quest(
        PoolProvider({"park": pools["park"][:1]}),
        _request(Occasion.solo, DayPart.morning, 2),
    )

    assert _names(solo)[0] == "Indiranagara Park"
    assert _names(family) == ["Defence Colony Children's Park"]
    # Still a fallback, not a reject: it is the only park there is.
    assert _names(only_kids) == ["Defence Colony Children's Park"]


def test_rage_room_is_not_a_date_stop_whatever_google_files_it_under(fake_narrative) -> None:
    """Google's primary type for it is `tourist_attraction`, so the type alone
    lets it through. It is ruled out by name, the way escape rooms are."""
    rage_room = PlaceItem(
        name="Rage Room", address="Road", lat=0.0, lng=0.0, distance_meters=0,
        rating=4.7, user_ratings_total=942, types=["tourist_attraction"],
        primary_type="tourist_attraction", provider_id="rage",
    )
    escape_rooms = rage_room.model_copy(update={
        "name": "Breakout® Escape Rooms | Koramangala", "provider_id": "escape",
    })

    for place in (rage_room, escape_rooms):
        assert _mood_reject_rule(place, Occasion.date, time(17, 30)) == "mood_name"
        assert _mood_reject_rule(place, Occasion.friends, time(17, 30)) is None

    provider = PoolProvider({
        "tourist_attraction": [
            _raw("rage", "Rage Room", "tourist_attraction", rating=4.7, reviews=942),
        ],
        "art_gallery": [_raw("gallery", "City Gallery", "art_gallery", rating=4.2, reviews=300)],
    })
    quest = _quest(provider, _request(Occasion.date, DayPart.evening, 1))
    assert _names(quest) == ["City Gallery"]


# ── Less chain and popularity bias for date and solo ──────────────────────────

def _item(provider_id: str, *, rating: float, reviews: int, price_level: int | None = 2) -> PlaceItem:
    return PlaceItem(
        name=provider_id, address="Road", lat=0.0, lng=0.0, distance_meters=0,
        rating=rating, user_ratings_total=reviews, price_level=price_level,
        types=["restaurant"], provider_id=provider_id,
    )


def test_popularity_is_capped_for_date_and_solo_food_only() -> None:
    for place_type in ("restaurant", "cafe", "bakery", "bar"):
        assert _popularity_cap(Occasion.date, place_type) == 3_000
        assert _popularity_cap(Occasion.solo, place_type) == 3_000
        assert _popularity_cap(Occasion.friends, place_type) is None
        assert _popularity_cap(Occasion.family, place_type) is None
    # For a park or a sight the count is what marks a destination.
    for place_type in ("park", "tourist_attraction", "art_gallery", "museum"):
        assert _popularity_cap(Occasion.date, place_type) is None
        assert _popularity_cap(Occasion.solo, place_type) is None


def test_capped_popularity_lets_a_better_rated_place_beat_the_chain() -> None:
    chain = _item("chain", rating=4.4, reviews=51_000)
    local = _item("local", rating=4.5, reviews=3_000)
    candidates = [chain, local]

    assert _pick(candidates, CostEstimate.mid, None, None, set()) == chain
    assert _pick(
        candidates, CostEstimate.mid, None, None, set(), popularity_cap=3_000
    ) == local


def test_below_the_cap_popularity_counts_as_before() -> None:
    known = _item("known", rating=4.4, reviews=2_500)
    obscure = _item("obscure", rating=4.5, reviews=110)

    for cap in (None, 3_000):
        assert _pick(
            [known, obscure], CostEstimate.mid, None, None, set(), popularity_cap=cap
        ) == known


def test_date_dinner_is_not_always_the_most_reviewed_place(fake_narrative) -> None:
    pools = {
        "restaurant": [
            _raw("chain", "Burger Chain", "hamburger_restaurant", tags=("restaurant",),
                 rating=4.4, reviews=51_000, price_level=2),
            _raw("local", "Garden Bistro", "italian_restaurant", tags=("restaurant",),
                 rating=4.5, reviews=3_000, price_level=2),
        ],
    }

    date = _quest(PoolProvider(pools), _request(Occasion.date, DayPart.night, 1))
    family = _quest(PoolProvider(pools), _request(Occasion.family, DayPart.night, 1))

    assert _names(date) == ["Garden Bistro"]
    # Uncapped occasions are untouched.
    assert _names(family) == ["Burger Chain"]


def test_the_citys_main_park_still_leads_a_solo_morning(fake_narrative) -> None:
    """Parks are not capped. For a park the review count is what tells the
    one the whole city goes to from a pleasant small one."""
    provider = PoolProvider({
        "park": [
            _raw("main", "Sri Chamarajendra Park", "park", lat=0.0100, rating=4.4, reviews=143_000),
            _raw("small", "Memorial Park", "park", lat=0.0110, rating=4.5, reviews=2_900),
        ],
        "cafe": _city()["cafe"],
    })

    quest = _quest(provider, _request(Occasion.solo, DayPart.morning, 2))

    assert _names(quest) == ["Sri Chamarajendra Park", "Corner Coffee"]
    # What the cap would do to the same two parks: the small one would lead.
    main_park, small_park = (
        _item("main", rating=4.4, reviews=143_000, price_level=None),
        _item("small", rating=4.5, reviews=2_900, price_level=None),
    )
    assert _pick(
        [main_park, small_park], CostEstimate.mid, None, None, set(), popularity_cap=3_000
    ) == small_park
    assert _pick([main_park, small_park], CostEstimate.mid, None, None, set()) == main_park


def test_strong_floors_are_unchanged(fake_narrative) -> None:
    assert (_STRONG_RATING_FLOOR, _STRONG_RATINGS_TOTAL_FLOOR) == (4.0, 100)
    assert not _is_strong(_item("low", rating=3.9, reviews=5_000))
    assert not _is_strong(_item("few", rating=4.8, reviews=99))
    # A place under the floor is not picked just because it is the right kind.
    provider = PoolProvider({
        "bar": [_raw("weak", "Quiet Pub", "pub", tags=("bar",), rating=3.9, reviews=5000)],
    })
    with pytest.raises(ValueError):
        _quest(provider, _request(Occasion.friends, DayPart.night, 1))


# ── Walking threshold ─────────────────────────────────────────────────────────

def test_a_walk_is_at_most_800_metres() -> None:
    assert _WALK_THRESHOLD_M == 800.0
    assert _travel_time(800.0) == (10, TravelMode.walking)
    assert _travel_time(801.0) == (2, TravelMode.driving)
    # 1.2 km was a 15-minute "walk"; it is a short ride now.
    assert _travel_time(1_200.0) == (3, TravelMode.driving)


def test_why_line_calls_a_kilometre_a_ride() -> None:
    place = _item("p", rating=4.0, reviews=120, price_level=None)

    assert _why(place, CostEstimate.mid, 700.0) == "An easy walk from the previous stop."
    assert _why(place, CostEstimate.mid, 1_000.0) == "A quick ride from the previous stop."


def test_frontend_travel_model_mirrors_the_backend() -> None:
    source_path = FRONTEND_SRC / "lib" / "questBuild.ts"
    if not source_path.is_file():
        pytest.skip("frontend sources are not in this checkout")
    source = source_path.read_text(encoding="utf-8")

    def constant(name: str) -> float:
        match = re.search(rf"^const {name} = ([\d_.]+)$", source, re.MULTILINE)
        assert match, f"{name} not found in questBuild.ts"
        return float(match.group(1).replace("_", ""))

    assert constant("WALK_THRESHOLD_M") == _WALK_THRESHOLD_M
    assert constant("WALK_M_PER_MIN") == _WALK_M_PER_MIN
    assert constant("DRIVE_M_PER_MIN") == _DRIVE_M_PER_MIN


# ── Titles and fallback text ──────────────────────────────────────────────────

_TIME_WORDS = {
    DayPart.morning: {"morning", "day"},
    DayPart.afternoon: {"afternoon", "day"},
    DayPart.evening: {"evening"},
    DayPart.night: {"night"},
}
_ALL_TIME_WORDS = {"morning", "afternoon", "evening", "night", "day"}


def test_no_title_names_a_time_of_day_other_than_its_own() -> None:
    for occasion in Occasion:
        for cost in CostEstimate:
            assert len(_TITLES[occasion][cost]) == len(DayPart)
            for day_part in DayPart:
                title = _quest_title(occasion, cost, "17.4,78.3", day_part)
                words = set(re.findall(r"[a-z]+", title.lower()))
                wrong = (words & _ALL_TIME_WORDS) - _TIME_WORDS[day_part]
                assert not wrong, f"{occasion.value}/{cost.value}/{day_part.value}: {title!r}"


def test_titles_follow_the_day_part() -> None:
    def title(occasion: Occasion, day_part: DayPart) -> str:
        return _quest_title(occasion, CostEstimate.mid, "Jubilee Hills, Hyderabad", day_part)

    assert title(Occasion.date, DayPart.evening) == "An Evening Date in Jubilee Hills"
    assert title(Occasion.date, DayPart.night) == "A Date Night in Jubilee Hills"
    assert title(Occasion.date, DayPart.morning) == "A Morning Date in Jubilee Hills"
    assert title(Occasion.solo, DayPart.morning) == "A Solo Day Out in Jubilee Hills"
    assert title(Occasion.solo, DayPart.evening) == "A Solo Evening Out in Jubilee Hills"
    assert title(Occasion.friends, DayPart.morning) == "A Morning with Friends in Jubilee Hills"
    assert title(Occasion.friends, DayPart.night) == "A Night Out with Friends in Jubilee Hills"


def test_fallback_narrative_matches_the_time_of_day() -> None:
    morning = _fallback_narrative(
        "Cubbon Park", "solo", "mid", ["the park", "the cafe", "the gallery"], "morning"
    )

    assert morning == (
        "A solo morning in Cubbon Park: start at the park, move on to the cafe, "
        "then finish at the gallery."
    )
    for occasion in _OUTING_PHRASES:
        for day_part in ("morning", "afternoon", "evening"):
            text = _fallback_narrative("X", occasion, "mid", ["a", "b", "c"], day_part)
            assert "night" not in text
        # "mid" is our name for a budget, not a word for the reader.
        for cost in ("cheap", "mid", "splurge"):
            text = _fallback_narrative("X", occasion, cost, ["a", "b"], "evening")
            assert "mid" not in text.split()


def test_fallback_narrative_reads_naturally_for_any_number_of_stops() -> None:
    def text(*stops: str, cost: str = "mid", day_part: str | None = "evening") -> str:
        return _fallback_narrative("Koramangala", "date", cost, list(stops), day_part)

    assert text() == "An evening date in Koramangala."
    assert text("A") == "An evening date in Koramangala, built around A."
    assert text("A", "B") == "An evening date in Koramangala: start at A, then finish at B."
    assert text("A", "B", "C", "D") == (
        "An evening date in Koramangala: start at A, move on to B and C, then finish at D."
    )
    assert text("A", cost="cheap") == "A budget-friendly evening date in Koramangala, built around A."
    assert text("A", cost="splurge", day_part="night") == (
        "A splurge-worthy date night in Koramangala, built around A."
    )
    # A caller that does not say when: no time of day is claimed.
    assert text("A", "B", day_part=None) == "A date in Koramangala: start at A, then finish at B."


def test_quest_text_is_told_the_time_of_day(fake_narrative) -> None:
    quest = _quest(PoolProvider(_city()), _request(Occasion.solo, DayPart.morning, 3))

    assert fake_narrative[0]["day_part"] == "morning"
    assert quest.title == "A Solo Day Out in Govindpuram"


def test_frontend_rebuilt_narrative_mirrors_the_backend_phrases() -> None:
    source_path = FRONTEND_SRC / "lib" / "narrative.ts"
    if not source_path.is_file():
        pytest.skip("frontend sources are not in this checkout")
    source = source_path.read_text(encoding="utf-8")

    for by_part in _OUTING_PHRASES.values():
        for day_part, phrase in by_part.items():
            if day_part is not None:
                assert f"{day_part}: '{phrase}'" in source
    for cost, word in _BUDGET_WORDS.items():
        assert f"{cost}: '{word}'" in source
    assert "finishing the night" not in source


# ── Caveats: sparse areas, shuffle, budget, rain, cost, compatibility ─────────

def test_area_with_one_restaurant_and_nothing_else_still_gets_a_plan(fake_narrative) -> None:
    """Whatever the plan wanted to open with, the one place there is gets used."""
    provider = PoolProvider({"restaurant": _city()["restaurant"]})

    for occasion in (Occasion.date, Occasion.friends, Occasion.family):
        for day_part in DayPart:
            for count in range(1, MAX_STOPS + 1):
                quest = _quest(provider, _request(occasion, day_part, count))
                assert _names(quest) == ["Garden Bistro"], (
                    f"{occasion.value}/{day_part.value}/{count}"
                )


def test_area_with_one_cafe_and_nothing_else_still_gets_a_plan(fake_narrative) -> None:
    provider = PoolProvider({"cafe": _city()["cafe"]})

    for occasion in Occasion:
        for day_part in DayPart:
            for count in range(1, MAX_STOPS + 1):
                quest = _quest(provider, _request(occasion, day_part, count))
                assert _names(quest) == ["Corner Coffee"], (
                    f"{occasion.value}/{day_part.value}/{count}"
                )


def test_solo_quest_has_never_searched_restaurants(fake_narrative) -> None:
    """Not new: a solo outing is a cafe and somewhere quiet, so an area with
    only a restaurant had no solo plan before either."""
    provider = PoolProvider({"restaurant": _city()["restaurant"]})

    with pytest.raises(ValueError):
        _quest(provider, _request(Occasion.solo, DayPart.morning, 3))
    assert "restaurant" not in {place_type for place_type, _ in provider.searches}


def test_area_with_nothing_at_all_fails_as_before(fake_narrative) -> None:
    with pytest.raises(ValueError):
        _quest(PoolProvider({}), _request(Occasion.date, DayPart.evening, 3))


def test_a_stop_that_cannot_be_filled_is_made_up_from_the_spares(fake_narrative) -> None:
    """No park, sight or gallery here. The evening date is still three stops:
    the dessert a four-stop version would have ended with takes the place."""
    city = _city()
    provider = PoolProvider({
        "cafe": city["cafe"], "restaurant": city["restaurant"], "bakery": city["bakery"],
    })

    quest = _quest(provider, _request(Occasion.date, DayPart.evening, 3))

    assert _names(quest) == ["Corner Coffee", "Garden Bistro", "Sweet Patisserie"]


def test_area_where_every_place_is_the_wrong_kind_still_fills_every_stop(fake_narrative) -> None:
    """Everything here is a restaurant by primary type. Each stop falls back
    to whatever carries its tag rather than going empty."""
    provider = PoolProvider({
        "park": [_raw("r1", "Garden Grill", "barbecue_restaurant", tags=("park",), lat=0.0010)],
        "cafe": [_raw("r2", "Cafe Curry", "indian_restaurant", tags=("cafe",), lat=0.0015)],
        "restaurant": [_raw("r3", "Fast Bites", "fast_food_restaurant", tags=("restaurant",), lat=0.0020)],
    })

    quest = _quest(provider, _request(Occasion.date, DayPart.evening, 3))

    assert _names(quest) == ["Garden Grill", "Cafe Curry", "Fast Bites"]


def _near_ties() -> dict[str, list[RawPlace]]:
    def several(kind: str, primary: str, tags: tuple[str, ...], base: float) -> list[RawPlace]:
        return [
            _raw(f"{kind}{i}", f"{kind.title()} {i}", primary, tags=tags, lat=base + 0.0002 * i)
            for i in range(4)
        ]

    return {
        "park": several("park", "park", (), 0.0010),
        "cafe": several("cafe", "cafe", (), 0.0020),
        "restaurant": several("diner", "italian_restaurant", ("restaurant",), 0.0030),
    }


def test_shuffle_still_produces_different_plans(fake_narrative) -> None:
    def plan(seed: int | None) -> tuple[str, ...]:
        req = _request(Occasion.date, DayPart.evening, 3, variety_seed=seed)
        return tuple(_names(_quest(PoolProvider(_near_ties()), req)))

    shuffled = {plan(seed) for seed in range(8)}

    assert len(shuffled) >= 3
    # The same seed is the same plan, and no seed is always the same plan.
    assert plan(5) == plan(5)
    assert plan(None) == plan(None)
    # Shuffling changes which places, never what kind of stop comes when.
    for names in shuffled:
        assert [name.split()[0] for name in names] == ["Park", "Cafe", "Diner"]


def test_shuffle_does_not_promote_the_wrong_kind_of_place(fake_narrative) -> None:
    provider = PoolProvider({
        "bar": [
            _raw("pub1", "Corner Pub", "pub", tags=("bar",)),
            _raw("pub2", "Other Pub", "pub", tags=("bar",)),
            _raw("pizza", "Slice House", "pizza_restaurant", tags=("bar",)),
        ],
    })

    picks = {
        _names(_quest(provider, _request(Occasion.friends, DayPart.night, 1, variety_seed=seed)))[0]
        for seed in range(12)
    }

    assert picks == {"Corner Pub", "Other Pub"}


def test_cheap_quest_passes_over_the_right_kind_of_place_when_it_costs_too_much(
    fake_narrative,
) -> None:
    """The budget promise outranks the kind of place: a known-expensive
    restaurant does not beat a cheap cafe that serves meals."""
    provider = PoolProvider({
        "restaurant": [
            _raw("pricey", "Tasting Room", "fine_dining_restaurant", tags=("restaurant",),
                 rating=4.9, reviews=9000, price_level=3),
            _raw("cheap", "Everyday Cafe", "cafe", tags=("restaurant",),
                 rating=4.1, reviews=150, price_level=1),
        ],
    })

    quest = _quest(provider, _request(Occasion.date, DayPart.night, 1, cost=CostEstimate.cheap))

    assert _names(quest) == ["Everyday Cafe"]
    # And no paid hours lookup was spent on the place that was never an option.
    assert "pricey" not in provider.hours_requested


def test_cheap_quest_keeps_the_expensive_place_only_as_a_last_resort(fake_narrative) -> None:
    provider = PoolProvider({
        "restaurant": [
            _raw("pricey", "Tasting Room", "fine_dining_restaurant", tags=("restaurant",),
                 rating=4.9, reviews=9000, price_level=3),
        ],
    })

    quest = _quest(provider, _request(Occasion.date, DayPart.night, 1, cost=CostEstimate.cheap))

    assert _names(quest) == ["Tasting Room"]


def test_rain_keeps_the_opening_walk_indoors(fake_narrative, monkeypatch) -> None:
    def quest(rainy: bool | None) -> Quest:
        async def forecast(lat: float, lng: float, start_hour: int) -> bool | None:
            return rainy

        monkeypatch.setattr("quest_generator.rain_expected", forecast)
        return _quest(PoolProvider(_city()), _request(Occasion.date, DayPart.evening, 3))

    wet = quest(True)
    assert _names(wet) == ["Old Fort", "Corner Coffee", "Garden Bistro"]
    assert wet.weather_note is not None

    for rainy in (False, None):
        dry = quest(rainy)
        assert _names(dry) == ["Lake Park", "Corner Coffee", "Garden Bistro"]
        assert dry.weather_note is None


def test_opening_stop_stays_near_the_searched_spot(fake_narrative) -> None:
    """A plan that opens with a park used to open with the most popular park
    in reach, and every later stop followed it out of the area."""
    provider = PoolProvider({
        "park": [
            _raw("far", "Famous Park", "park", lat=0.0255, rating=4.4, reviews=9_000),
            _raw("near", "Local Park", "park", lat=0.0045, rating=4.4, reviews=3_000),
        ],
        "cafe": [
            _raw("far_cafe", "Cafe By Famous Park", "cafe", lat=0.0256),
            _raw("near_cafe", "Cafe By Local Park", "cafe", lat=0.0046),
        ],
    })

    quest = _quest(provider, _request(Occasion.solo, DayPart.morning, 2))

    assert _names(quest) == ["Local Park", "Cafe By Local Park"]


def test_first_stop_fit_is_flat_nearby_and_falls_away_beyond() -> None:
    assert _first_stop_fit(0.0) == _first_stop_fit(_FIRST_STOP_NEAR_M) == 0.66
    assert _first_stop_fit(3_000.0) == pytest.approx(0.33)
    assert _first_stop_fit(10_000.0) < _first_stop_fit(6_000.0) < _first_stop_fit(3_000.0)


def test_hours_are_looked_up_once_per_place_in_a_request(fake_narrative) -> None:
    """Both passes over a stop look at the same place; the lookup is a paid
    call, so the second pass reuses the first one's answer."""
    provider = PoolProvider(
        {"bar": [_raw("pub", "Corner Pub", "pub", tags=("bar",))]},
        hours={"pub": HOURS_UNKNOWN},
    )

    quest = _quest(provider, _request(Occasion.friends, DayPart.night, 1))

    # Unknown hours: not good enough for the first pass, kept by the second.
    assert _names(quest) == ["Corner Pub"]
    assert provider.hours_requested == ["pub"]


def test_response_only_gains_optional_fields(fake_narrative) -> None:
    quest = _quest(PoolProvider(_city()), _request(Occasion.date, DayPart.evening, 3))
    body = quest.model_dump(mode="json")

    assert {
        "id", "title", "occasion", "stops", "total_duration_minutes",
        "total_cost_estimate", "est_total_per_person_min_inr",
        "est_total_per_person_max_inr", "weather_note", "created_by",
        "narrative", "created_at",
    } <= set(body)
    stop = body["stops"][0]
    assert {
        "place", "category", "time_block_start", "time_block_end",
        "travel_to_next_minutes", "travel_mode", "why_this_place",
        "est_cost_per_person_min_inr", "est_cost_per_person_max_inr", "price_source",
    } == set(stop)
    assert stop["place"]["primary_type"] == "park"
    assert not PlaceItem.model_fields["primary_type"].is_required()

    # A quest saved before the field existed still loads.
    for saved_stop in body["stops"]:
        del saved_stop["place"]["primary_type"]
    reloaded = Quest.model_validate(body)
    assert reloaded.stops[0].place.primary_type is None


# ── Swapping a stop ───────────────────────────────────────────────────────────

def _saved_quest(category: StopCategory, place_types: list[str]) -> Quest:
    return Quest(
        title="A Night Out with Friends",
        occasion=Occasion.friends,
        stops=[
            Stop(
                place=PlaceItem(
                    name="The Old Pick", address="Road", lat=0.0, lng=0.0,
                    distance_meters=0, rating=4.2, user_ratings_total=500,
                    types=place_types, provider_id="original",
                ),
                category=category,
                time_block_start=time(20, 0),
                time_block_end=time(20, 45),
                why_this_place="A solid local choice.",
            ),
        ],
        total_duration_minutes=45,
        total_cost_estimate=CostEstimate.mid,
        narrative="A test quest.",
    )


def _alternatives(provider: PoolProvider, quest: Quest, body: dict | None = None) -> list[dict]:
    app.dependency_overrides[get_nearby_places_service] = lambda: NearbyPlacesService(provider)
    try:
        response = TestClient(app).post(
            f"/api/quest/{quest.id}/stop/0/alternatives",
            json=body if body is not None else quest.model_dump(mode="json"),
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    return response.json()


def test_swap_offers_the_same_kind_of_place_first() -> None:
    provider = PoolProvider({
        "bar": [
            _raw("pizza", "Slice House", "pizza_restaurant", tags=("bar",),
                 rating=4.8, reviews=9000, price_level=2),
            _raw("pub", "Corner Pub", "pub", tags=("bar",), rating=4.1, reviews=300),
        ],
    })

    offered = _alternatives(provider, _saved_quest(StopCategory.bar, ["bar"]))

    # Bars before the pizzeria that carries the tag; the pizzeria is still there.
    assert [alt["place"]["name"] for alt in offered] == ["Corner Pub", "Slice House"]
    assert offered[0]["category"] == "bar"
    assert offered[0]["place"]["primary_type"] == "pub"


def test_swap_works_for_a_quest_saved_before_primary_types() -> None:
    quest = _saved_quest(StopCategory.other, ["bakery", "cafe"])
    body = quest.model_dump(mode="json")
    for stop in body["stops"]:
        del stop["place"]["primary_type"]
    provider = PoolProvider({
        "bakery": [
            _raw("cakes", "Designer Cakes", "bakery", rating=4.9, reviews=1200),
            _raw("patisserie", "Sweet Patisserie", "bakery", tags=("cafe",), rating=4.2, reviews=400),
        ],
    })

    offered = _alternatives(provider, quest, body)

    assert [alt["place"]["name"] for alt in offered] == ["Sweet Patisserie", "Designer Cakes"]
