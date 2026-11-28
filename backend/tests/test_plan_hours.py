"""Every plan asks for places at an hour when they are usually open.

The hours check drops a shut place, but a plan that asks for a park at 21:30
pays for searches that cannot succeed and ends on whatever is left. So the
shapes themselves are checked: each occasion, day part and stop count is
scheduled with every place open, and each stop's main search type is held
to the hours such places typically keep.
"""

import asyncio

import pytest

from models import CostEstimate, DayPart, Occasion, QuestGenerationRequest, StopCategory
from quest_generator import _swap_kind, assemble_quest
from quest_templates import (
    CAFE,
    DESSERT,
    MAX_STOPS,
    PLANS,
    TREAT,
)
from services.nearby_places_service import NearbyPlacesService
from services.places_provider import PlaceHours, RawPlace, ResolvedLocation

# Typical opening hours, in minutes after midnight, for the first type a stop
# searches. An assumption about most places of the kind, not a rule Google
# enforces: the real hours check still runs on every candidate.
TYPICAL_HOURS = {
    "park": (5 * 60, 20 * 60),
    "tourist_attraction": (9 * 60, 18 * 60),
    "museum": (10 * 60, 17 * 60 + 30),
    "art_gallery": (11 * 60, 19 * 60),
    "zoo": (9 * 60, 17 * 60),
    "aquarium": (10 * 60, 19 * 60),
    "amusement_park": (11 * 60, 19 * 60 + 30),
    "library": (9 * 60, 20 * 60),
    "book_store": (10 * 60, 21 * 60 + 30),
    "shopping_mall": (10 * 60, 22 * 60),
    "bowling_alley": (11 * 60, 23 * 60 + 30),
    "movie_theater": (9 * 60, 25 * 60),
    "cafe": (8 * 60, 23 * 60),
    "bakery": (8 * 60, 23 * 60),
    "restaurant": (12 * 60, 23 * 60 + 30),
    "bar": (12 * 60, 25 * 60),
    "night_club": (20 * 60, 26 * 60),
}
# Daylight kinds: none of these may be asked for once dinner is over.
DAYLIGHT_TYPES = {"park", "tourist_attraction", "museum", "art_gallery", "zoo",
                  "aquarium", "amusement_park", "library"}


class EverythingOpen:
    """Six places of every type a short walk apart, open around the clock."""

    async def geocode(self, query: str) -> ResolvedLocation:
        return ResolvedLocation(name=query, lat=0.0, lng=0.0)

    async def nearby_by_type(self, *, lat, lng, radius_meters, place_type, target_count=None):
        primary = {"restaurant": "italian_restaurant"}.get(place_type, place_type)
        tags = [place_type] + (["cafe"] if place_type == "bakery" else [])
        return [
            RawPlace(f"{place_type}{k}", f"{place_type} {k}", "Road", 0.003 * (k + 1), 0.0,
                     4.5, tags, 900, primary_type=primary)
            for k in range(6)
        ]

    async def place_hours(self, *, provider_id: str, weekday: int) -> PlaceHours:
        return PlaceHours(None, None, True)


@pytest.fixture(autouse=True)
def fake_narrative(monkeypatch):
    async def _narrative(**kwargs) -> str:
        return "A test quest."

    monkeypatch.setattr("quest_generator.generate_quest_narrative", _narrative)


def _schedule(occasion: Occasion, day_part: DayPart, count: int):
    req = QuestGenerationRequest(
        location="Somewhere", occasion=occasion, cost_estimate=CostEstimate.mid,
        people=2, stop_count=count, day_part=day_part,
    )
    quest = asyncio.run(assemble_quest(req, NearbyPlacesService(EverythingOpen())))
    return list(zip(PLANS[occasion][day_part].stops(count), quest.stops))


def _span(stop) -> tuple[int, int]:
    start = stop.time_block_start.hour * 60 + stop.time_block_start.minute
    end = stop.time_block_end.hour * 60 + stop.time_block_end.minute
    if end < start:
        end += 24 * 60
    if start < 4 * 60:  # after midnight
        start, end = start + 24 * 60, end + 24 * 60
    return start, end


ALL_SHAPES = [
    (occasion, day_part, count)
    for occasion in Occasion
    for day_part in DayPart
    for count in range(1, MAX_STOPS + 1)
]


@pytest.mark.parametrize("occasion, day_part, count", ALL_SHAPES)
def test_every_stop_is_planned_when_its_kind_of_place_is_open(occasion, day_part, count) -> None:
    for tmpl, stop in _schedule(occasion, day_part, count):
        main_type = tmpl.places_types[0]
        opens, closes = TYPICAL_HOURS[main_type]
        start, end = _span(stop)
        assert opens <= start and end <= closes, (
            f"{occasion.value}/{day_part.value}/{count}: {tmpl.role} ({main_type}) "
            f"at {stop.time_block_start:%H:%M}-{stop.time_block_end:%H:%M}"
        )


@pytest.mark.parametrize("occasion", list(Occasion))
def test_a_night_plan_asks_for_nothing_that_keeps_daylight_hours(occasion) -> None:
    plan = PLANS[occasion][DayPart.night]
    for tmpl in plan.sequence:
        assert not DAYLIGHT_TYPES & set(tmpl.places_types), (occasion.value, tmpl.places_types)


def test_two_stops_with_friends_in_the_evening_include_dinner() -> None:
    stops = _schedule(Occasion.friends, DayPart.evening, 2)
    assert [tmpl.role for tmpl, _ in stops] == ["activity", "meal"]
    assert stops[1][1].time_block_start.hour == 19


def test_solo_night_is_dinner_a_film_and_somewhere_open_late() -> None:
    plan = PLANS[Occasion.solo][DayPart.night]
    assert [t.role for t in plan.stops(1)] == ["dessert"]
    assert [t.role for t in plan.stops(2)] == ["meal", "dessert"]
    assert [t.places_types[0] for t in plan.stops(3)] == ["restaurant", "movie_theater", "bakery"]


def test_only_a_family_night_is_shorter() -> None:
    for occasion in Occasion:
        for day_part in DayPart:
            plan = PLANS[occasion][day_part]
            expected = 3 if (occasion, day_part) == (Occasion.family, DayPart.night) else MAX_STOPS
            assert len(plan.stops(MAX_STOPS)) == expected, (occasion.value, day_part.value)
    # A family night of four stops is the same three: dinner, a treat, then
    # bowling or a film, over before about 22:45.
    stops = _schedule(Occasion.family, DayPart.night, 4)
    assert [tmpl.role for tmpl, _ in stops] == ["meal", "dessert", "activity"]
    assert _span(stops[-1][1])[1] <= 23 * 60


def test_dessert_reads_as_a_cafe() -> None:
    assert DESSERT.category == StopCategory.cafe
    assert TREAT.category == StopCategory.cafe


def _stop(category: StopCategory, primary_type: str):
    from models import PlaceItem, Stop

    place = PlaceItem(name="X", address="Y", lat=0, lng=0, distance_meters=0,
                      provider_id="x", primary_type=primary_type, types=[primary_type])
    return Stop(place=place, category=category, time_block_start="20:00",
                time_block_end="20:40", why_this_place="Good.")


def test_swapping_a_dessert_stop_still_offers_dessert_first() -> None:
    # Made since this change: a café at a bakery or sweet shop is dessert.
    assert _swap_kind(_stop(StopCategory.cafe, "bakery"), "cafe", Occasion.date) is DESSERT
    assert _swap_kind(_stop(StopCategory.cafe, "ice_cream_shop"), "cafe", Occasion.family) is TREAT
    # A coffee stop stays a coffee stop.
    assert _swap_kind(_stop(StopCategory.cafe, "coffee_shop"), "cafe", Occasion.date) is CAFE
    # Made before: "other" at a bakery.
    assert _swap_kind(_stop(StopCategory.other, "bakery"), "bakery", Occasion.date) is DESSERT
