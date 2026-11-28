"""A park is kept out of the midday window only when the day is hot."""

import asyncio
from datetime import date, timedelta

import pytest

from models import Occasion
from services import weather_service
from tests.test_start_time import TODAY, Pools, _names, _open_city, _req, _run

PLAN_DAY = TODAY + timedelta(days=3)


def _forecast(monkeypatch, temps_by_day: dict[date, dict[int, float]] | None) -> list:
    asked: list = []

    async def fake(lat, lng, on_date=None):
        asked.append(on_date)
        if temps_by_day is None:
            return None
        return temps_by_day.get(on_date)

    monkeypatch.setattr("quest_generator.place_feels_like", fake)
    return asked


def _noon_walk() -> str:
    """A solo morning chosen for 11:00, inside the midday window: a walk first."""
    quest = _run(Pools(_open_city()), _req(Occasion.solo, stops=2, start_date=PLAN_DAY, start_time="11:00"))
    return quest.stops[0].place.primary_type


def test_a_hot_noon_keeps_the_park_out(monkeypatch) -> None:
    _forecast(monkeypatch, {PLAN_DAY: {11: 31.0}})
    assert _noon_walk() != "park"


def test_a_cool_noon_has_its_park(monkeypatch) -> None:
    _forecast(monkeypatch, {PLAN_DAY: {11: 22.5}})
    assert _noon_walk() == "park"


def test_just_at_the_threshold_counts_as_hot(monkeypatch) -> None:
    _forecast(monkeypatch, {PLAN_DAY: {11: 27.0}})
    assert _noon_walk() != "park"


def test_no_forecast_keeps_the_park_out_as_before(monkeypatch) -> None:
    _forecast(monkeypatch, None)
    assert _noon_walk() != "park"


def test_the_hour_missing_from_the_forecast_counts_as_hot(monkeypatch) -> None:
    _forecast(monkeypatch, {PLAN_DAY: {9: 20.0}})
    assert _noon_walk() != "park"


def test_the_forecast_is_read_for_the_chosen_day(monkeypatch) -> None:
    """Hot today, cool on the day chosen later in the week: the park is in."""
    asked = _forecast(monkeypatch, {TODAY: {11: 33.0}, PLAN_DAY: {11: 21.0}})
    assert _noon_walk() == "park"
    assert asked == [PLAN_DAY]


def test_feels_like_hours_come_from_the_chosen_day(monkeypatch) -> None:
    async def fake_forecast(lat, lng):
        return {"hourly": {
            "time": ["2026-12-01T12:00", "2026-12-01T13:00", "2026-12-03T12:00"],
            "apparent_temperature": [30.1, None, 21.4],
        }}

    monkeypatch.setattr(weather_service, "_forecast", fake_forecast)
    on = asyncio.run(weather_service.feels_like_by_hour(0, 0, date(2026, 12, 3)))
    first = asyncio.run(weather_service.feels_like_by_hour(0, 0))
    assert on == {12: 21.4}
    assert first == {12: 30.1}


@pytest.mark.parametrize("start", ["08:00", "16:30"])
def test_outside_the_window_the_temperature_does_not_matter(monkeypatch, start) -> None:
    _forecast(monkeypatch, {PLAN_DAY: {8: 35.0, 16: 35.0}})
    quest = _run(Pools(_open_city()), _req(Occasion.solo, stops=2, start_date=PLAN_DAY, start_time=start))
    assert quest.stops[0].place.primary_type == "park"
