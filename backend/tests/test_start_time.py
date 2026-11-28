"""A quest for a chosen day and start time, judged at the place's own clock."""

import asyncio
from datetime import date, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient

import quest_generator
from deps import get_nearby_places_service
from main import app
from models import CostEstimate, DayPart, Occasion, PlaceItem, QuestGenerationRequest
from quest_generator import (
    _Calendar,
    _meal_can_start,
    _slot_fits_hours,
    _types_for_the_hour,
    _window_for_slot,
    assemble_quest,
)
from quest_templates import CAFE, DINNER, MEAL, PLAY, SIGHT, STROLL
from services.google_places import _new_periods_to_legacy
from services.nearby_places_service import NearbyPlacesService
from services.places_provider import PlaceHours, RawPlace, ResolvedLocation, hours_for_weekday
from services.weather_service import _window_max_probability

# Fixed days, for the calendar arithmetic that is not validated.
FRIDAY = date(2026, 11, 27)
SATURDAY = FRIDAY + timedelta(days=1)
# Days a request may name: within the coming week of whenever this runs.
TODAY = datetime.utcnow().date()


def _next(weekday: int) -> date:
    """The next date (today or later) with Python weekday `weekday`."""
    return TODAY + timedelta(days=(weekday - TODAY.weekday()) % 7)


NEXT_FRIDAY = _next(4)
NEXT_MONDAY = _next(0)
SUN, MON, TUE, WED, THU, FRI, SAT = range(7)  # Google's weekday numbers


def _every_day(open_h: int, close_h: int, days=range(7)) -> list[dict]:
    """Opening periods in Places API (New) shape; a close past 24 runs into
    the next day."""
    out = []
    for d in days:
        close_day = (d + close_h // 24) % 7
        out.append({
            "open": {"day": d, "hour": open_h, "minute": 0},
            "close": {"day": close_day, "hour": close_h % 24, "minute": 0},
        })
    return out


def _place(pid: str, primary: str, periods: list[dict] | None, *, lat=0.002,
           reviews=900, offset: int | None = 330) -> RawPlace:
    tags = [primary] + (["cafe"] if primary == "bakery" else [])
    return RawPlace(
        pid, pid.replace("_", " ").title(), "Road", lat, 0.0, 4.5, tags, reviews,
        primary_type=primary,
        opening_periods=tuple(_new_periods_to_legacy(periods)) if periods is not None else None,
        utc_offset_minutes=offset,
    )


class Pools:
    def __init__(self, pools: dict[str, list[RawPlace]]) -> None:
        self.pools = pools
        self.searched: list[str] = []

    async def geocode(self, query: str) -> ResolvedLocation:
        return ResolvedLocation(name=query, lat=0.0, lng=0.0)

    async def nearby_by_type(self, *, lat, lng, radius_meters, place_type, target_count=None):
        self.searched.append(place_type)
        return list(self.pools.get(place_type, []))

    async def place_hours(self, *, provider_id: str, weekday: int) -> PlaceHours:
        raise AssertionError("hours come with the search")


@pytest.fixture(autouse=True)
def fake_narrative(monkeypatch):
    async def _narrative(**kwargs) -> str:
        return "A test quest."

    monkeypatch.setattr("quest_generator.generate_quest_narrative", _narrative)


def _req(occasion=Occasion.friends, stops=3, **extra) -> QuestGenerationRequest:
    return QuestGenerationRequest(location="Somewhere", occasion=occasion,
                                  cost_estimate=CostEstimate.mid, people=2,
                                  stop_count=stops, **extra)


def _run(provider, req):
    return asyncio.run(assemble_quest(req, NearbyPlacesService(provider)))


def _names(quest) -> list[str]:
    return [s.place.name for s in quest.stops]


# ── The weekday, and midnight ────────────────────────────────────────────────

def _item(offset: int | None = None) -> PlaceItem:
    return PlaceItem(name="X", address="Y", lat=0, lng=0, distance_meters=0,
                     provider_id="x", utc_offset_minutes=offset)


def test_the_chosen_day_decides_the_weekday() -> None:
    calendar = _Calendar(day=FRIDAY, start_min=20 * 60)
    assert calendar.weekday_g(_item(), time(20, 0)) == FRI
    assert calendar.weekday_g(_item(), time(23, 30)) == FRI


def test_a_visit_after_midnight_falls_on_the_next_day() -> None:
    calendar = _Calendar(day=FRIDAY, start_min=21 * 60)
    assert calendar.weekday_g(_item(), time(0, 30)) == SAT
    # Saturday night into Sunday wraps the week.
    assert _Calendar(day=SATURDAY, start_min=21 * 60).weekday_g(_item(), time(1, 0)) == SUN


def test_without_a_chosen_day_today_is_the_places_today(monkeypatch) -> None:
    class Clock(datetime):
        @classmethod
        def utcnow(cls):  # Saturday 20:00 UTC
            return datetime(2026, 11, 28, 20, 0)

    monkeypatch.setattr(quest_generator, "datetime", Clock)
    calendar = _Calendar(day=None, start_min=0)
    # 01:30 on Sunday in a place 5h30 ahead; 15:00 on Saturday 5h behind.
    assert calendar.weekday_g(_item(330), time(10, 0)) == SUN
    assert calendar.weekday_g(_item(-300), time(10, 0)) == SAT
    # A place with no offset of its own uses the area's.
    assert _Calendar(day=None, start_min=0, utc_offset_min=330).weekday_g(_item(), time(10, 0)) == SUN


def test_last_nights_hours_count_after_midnight() -> None:
    # Open Friday 18:00 to Saturday 02:00, and nothing else.
    periods = _new_periods_to_legacy(_every_day(18, 26, days=[FRI]))
    saturday = hours_for_weekday(periods, SAT)
    opens, closes = _window_for_slot(saturday, time(0, 30), time(1, 15))
    place = _item().model_copy(update={"opens_today": opens, "closes_today": closes})
    assert _slot_fits_hours(place, time(0, 30), time(1, 15))
    # Saturday's own opening (none) is unchanged.
    assert saturday.opens_today is None


def test_a_night_out_past_midnight_ends_where_it_is_still_open() -> None:
    late_bar = _place("late_bar", "bar", _every_day(18, 26, days=[FRI]))
    pools = {
        "restaurant": [_place("dinner_spot", "italian_restaurant", _every_day(12, 23))],
        "bowling_alley": [_place("lanes", "bowling_alley", _every_day(11, 26))],
        "bar": [late_bar],
    }
    req = _req(stops=3, start_date=NEXT_FRIDAY, start_time="22:00")
    quest = _run(Pools(pools), req)
    assert _names(quest)[-1] == "Late Bar"
    assert quest.stops[-1].time_block_start < time(4, 0)  # after midnight

    # The same plan on a Thursday: the bar is shut, so it is not the last stop.
    thursday = _run(Pools(pools), _req(stops=3, start_date=_next(3), start_time="22:00"))
    assert "Late Bar" not in _names(thursday)


def test_a_place_shut_on_the_chosen_weekday_is_passed_over() -> None:
    not_mondays = _place("not_mondays", "italian_restaurant",
                         _every_day(12, 23, days=[SUN, TUE, WED, THU, FRI, SAT]), reviews=5000)
    every_day = _place("every_day", "italian_restaurant", _every_day(12, 23), reviews=500)
    pools = {"restaurant": [not_mondays, every_day]}
    monday = _run(Pools(pools), _req(Occasion.date, stops=1, start_date=NEXT_MONDAY, start_time="20:00"))
    tuesday = _run(Pools(pools), _req(Occasion.date, stops=1, start_date=_next(1), start_time="20:00"))
    assert _names(monday) == ["Every Day"]
    assert _names(tuesday) == ["Not Mondays"]


# ── A time already past, and a start too late ─────────────────────────────────

def _clock(monkeypatch, utc: datetime, offset: int = 330) -> None:
    class Clock(datetime):
        @classmethod
        def utcnow(cls):
            return utc

    monkeypatch.setattr(quest_generator, "datetime", Clock)

    async def _offset(lat, lng):
        return offset

    monkeypatch.setattr("quest_generator.place_utc_offset", _offset)


def _open_city() -> dict[str, list[RawPlace]]:
    always = _every_day(0, 24)
    return {t: [_place(f"{t}_one", p, always)] for t, p in {
        "restaurant": "italian_restaurant", "cafe": "cafe", "bakery": "bakery",
        "bar": "bar", "park": "park", "tourist_attraction": "tourist_attraction",
        "art_gallery": "art_gallery", "museum": "museum", "bowling_alley": "bowling_alley",
        "movie_theater": "movie_theater",
    }.items()}


def test_a_start_already_past_today_moves_to_the_next_quarter_hour(monkeypatch) -> None:
    # 12:05 UTC is 17:35 at a place 5h30 ahead.
    _clock(monkeypatch, datetime.combine(TODAY, time(12, 5)))
    quest = _run(Pools(_open_city()),
                 _req(Occasion.solo, stops=2, start_date=TODAY, start_time="10:00"))
    assert quest.stops[0].time_block_start == time(17, 45)


def test_a_start_later_today_or_on_another_day_is_kept(monkeypatch) -> None:
    _clock(monkeypatch, datetime.combine(TODAY, time(4, 0)))  # 09:30 there
    later = _run(Pools(_open_city()), _req(Occasion.solo, stops=1, start_date=TODAY, start_time="10:00"))
    tomorrow = _run(Pools(_open_city()), _req(Occasion.solo, stops=1,
                                               start_date=TODAY + timedelta(days=1),
                                               start_time="08:00"))
    assert later.stops[0].time_block_start == time(10, 0)
    assert tomorrow.stops[0].time_block_start == time(8, 0)


def test_too_late_to_start_today_is_said_plainly(monkeypatch) -> None:
    _clock(monkeypatch, datetime.combine(TODAY, time(16, 50)))  # 22:20 there
    with pytest.raises(ValueError, match="already late"):
        _run(Pools(_open_city()), _req(start_date=TODAY, start_time="20:00"))


@pytest.mark.parametrize("bad, message", [
    ({"start_time": "06:30"}, "from 7 am"),
    ({"start_time": "22:30"}, "after 10 pm"),
    ({"start_time": "7pm"}, "pattern"),
    ({"start_date": (datetime.utcnow() + timedelta(days=12)).date().isoformat()}, "next week"),
])
def test_the_api_refuses_an_impossible_start_in_words(bad, message) -> None:
    body = {"location": "Somewhere", "occasion": "date", "cost_estimate": "mid", **bad}
    app.dependency_overrides[get_nearby_places_service] = lambda: NearbyPlacesService(Pools({}))
    try:
        res = TestClient(app).post("/api/quest/generate", json=body)
    finally:
        app.dependency_overrides.clear()
    assert res.status_code == 422
    assert message in res.text


# ── Stops follow the clock ────────────────────────────────────────────────────

def test_a_park_at_8_am_but_not_at_11_am() -> None:
    """The owner's example."""
    early = _run(Pools(_open_city()), _req(Occasion.solo, stops=2, start_time="08:00"))
    late = _run(Pools(_open_city()), _req(Occasion.solo, stops=2, start_time="11:00"))
    assert early.stops[0].place.primary_type == "park"
    assert late.stops[0].place.primary_type != "park"
    assert late.stops[0].time_block_start == time(11, 0)


def test_a_park_is_fine_again_late_in_the_afternoon() -> None:
    assert "park" in _types_for_the_hour(STROLL, 16 * 60 + 30)
    assert "park" not in _types_for_the_hour(STROLL, 13 * 60)
    assert "park" in _types_for_the_hour(STROLL, 9 * 60)


def test_no_sight_starts_after_dark() -> None:
    assert _types_for_the_hour(SIGHT, 19 * 60 + 15) == ()
    # A stop with something open late keeps just that.
    assert set(_types_for_the_hour(PLAY, 19 * 60 + 15)) == {"bowling_alley", "movie_theater", "shopping_mall"}
    assert _types_for_the_hour(CAFE, 21 * 60) == CAFE.places_types


def test_meals_keep_to_meal_hours() -> None:
    assert _meal_can_start(DINNER, 19 * 60, 0)
    assert _meal_can_start(DINNER, 17 * 60 + 40, 30)  # held to 18:10
    assert not _meal_can_start(DINNER, 16 * 60 + 30, 30)
    assert _meal_can_start(MEAL, 9 * 60, 0)  # breakfast
    assert _meal_can_start(MEAL, 13 * 60, 0)
    assert not _meal_can_start(MEAL, 16 * 60 + 30, 30)


def test_a_date_at_three_is_not_dinner_at_seven() -> None:
    """A two-stop evening date is built around dinner at 19:00; chosen for
    15:00 it is the long evening plan cut to two stops instead."""
    afternoon = _run(Pools(_open_city()), _req(Occasion.date, stops=2, start_time="15:00"))
    evening = _run(Pools(_open_city()), _req(Occasion.date, stops=2, start_time="17:30"))
    assert afternoon.stops[0].time_block_start == time(15, 0)
    assert all(s.category.value != "restaurant" for s in afternoon.stops)
    assert evening.stops[0].time_block_start == time(19, 0)
    assert evening.stops[0].category.value == "restaurant"


def test_the_start_time_wins_over_the_day_part() -> None:
    quest = _run(Pools(_open_city()), _req(Occasion.date, stops=1, start_time="13:30",
                                          day_part=DayPart.evening))
    # Planned (and named) as the afternoon it is: lunch at 13:30.
    assert quest.stops[0].time_block_start == time(13, 30)
    assert quest.stops[0].category.value == "restaurant"


def test_shuffle_keeps_the_chosen_day_and_time() -> None:
    pools = _open_city()
    pools["cafe"] = [_place(f"cafe_{i}", "cafe", _every_day(0, 24)) for i in range(5)]
    first = _run(Pools(pools), _req(Occasion.solo, stops=1, start_date=NEXT_FRIDAY, start_time="16:30"))
    again = _run(Pools(pools), _req(Occasion.solo, stops=1, start_date=NEXT_FRIDAY, start_time="16:30",
                                    variety_seed=7))
    assert first.stops[0].time_block_start == again.stops[0].time_block_start == time(16, 30)


def test_a_request_from_before_this_change_plans_as_before() -> None:
    quest = _run(Pools(_open_city()), _req(Occasion.date, stops=2, day_part=DayPart.evening))
    assert quest.stops[0].time_block_start == time(19, 0)


# ── The forecast, for the chosen day ──────────────────────────────────────────

def test_the_rain_check_reads_the_chosen_day() -> None:
    hourly = {
        "time": ["2026-11-28T18:00", "2026-11-28T19:00", "2026-11-29T18:00", "2026-11-29T19:00"],
        "precipitation_probability": [10, 10, 90, 80],
    }
    assert _window_max_probability(hourly, 18) == 10
    assert _window_max_probability(hourly, 18, on_date=date(2026, 11, 29)) == 90
