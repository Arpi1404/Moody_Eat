"""Swapping a stop for a different kind of place, and adding a stop."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from config import get_settings
from deps import get_nearby_places_service
from main import app
from models import (
    ALLOWED_NEARBY_TYPES,
    FILM_MINUTES,
    STOP_KIND_SEARCHES,
    CostEstimate,
    PlaceItem,
    StopKind,
)
from quest_generator import _DWELL, _why
from services.nearby_places_service import NearbyPlacesService
from services.places_provider import RawPlace
from tests.test_nearby_places import FakeProvider, _quest_payload

QUEST_ID = "11111111-1111-4111-8111-111111111111"
FRONTEND_SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"


class KindProvider(FakeProvider):
    """Returns strong places of whatever type was asked for."""

    def __init__(self, *, empty: bool = False) -> None:
        super().__init__(empty_nearby=empty)

    async def nearby_by_type(self, *, lat, lng, radius_meters, place_type, target_count=None):
        self.nearby_types.append(place_type)
        if self.empty_nearby:
            return []
        return [
            # Already stops in the quest: must never be offered.
            RawPlace("prev", "Previous Place", "Prev Road", 0.0, 0.0, 4.9, [place_type], 900),
            RawPlace("next", "Next Place", "Next Road", 0.002, 0.0, 4.9, [place_type], 900),
            RawPlace(f"{place_type}_a", "Alpha Spot", "A Road", 0.0005, 0.0, 4.8, [place_type], 800),
            RawPlace(f"{place_type}_b", "Beta Spot", "B Road", 0.004, 0.0, 4.5, [place_type], 500),
        ]


def _post(path: str, payload: dict, provider: FakeProvider):
    service = NearbyPlacesService(provider, get_settings())
    app.dependency_overrides[get_nearby_places_service] = lambda: service
    try:
        with TestClient(app) as client:
            return client.post(f"/api/quest/{QUEST_ID}/{path}", json=payload)
    finally:
        app.dependency_overrides.clear()


def _minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")[:2]
    return int(hours) * 60 + int(minutes)


def _dwell_of(stop: dict) -> int:
    return _minutes(stop["time_block_end"]) - _minutes(stop["time_block_start"])


def test_every_kind_searches_one_supported_type() -> None:
    assert set(STOP_KIND_SEARCHES) == set(StopKind)
    for places_type, category in STOP_KIND_SEARCHES.values():
        assert places_type in ALLOWED_NEARBY_TYPES
        assert category in _DWELL


@pytest.mark.parametrize("kind", list(StopKind))
def test_swap_by_kind_searches_that_type_once(kind: StopKind) -> None:
    provider = KindProvider()
    res = _post(f"stop/1/alternatives?kind={kind.value}", _quest_payload(), provider)

    places_type, category = STOP_KIND_SEARCHES[kind]
    assert res.status_code == 200
    assert provider.nearby_types == [places_type]
    body = res.json()
    assert {s["place"]["provider_id"] for s in body} == {f"{places_type}_a", f"{places_type}_b"}
    assert all(s["category"] == category.value and s["kind"] == kind.value for s in body)


def test_swap_without_kind_keeps_type_category_and_dwell() -> None:
    provider = KindProvider()
    res = _post("stop/1/alternatives", _quest_payload(), provider)

    assert res.status_code == 200
    assert provider.nearby_types == ["restaurant"]
    for stop in res.json():
        assert stop["category"] == "restaurant"
        assert stop["kind"] is None
        assert _dwell_of(stop) == 60


def test_swap_to_another_kind_uses_that_kinds_dwell_and_counts_it_in_the_delta() -> None:
    res = _post("stop/1/alternatives?kind=coffee", _quest_payload(), KindProvider())

    best = res.json()[0]
    assert _dwell_of(best) == 40  # a coffee, not the dinner's hour
    # Travel barely changes this close in, so the stop ends up about 20 min shorter.
    assert -23 <= best["delta"]["time_change_minutes"] <= -17


def test_swap_within_the_same_category_keeps_the_stops_own_dwell() -> None:
    payload = _quest_payload()
    payload["stops"][1]["time_block_end"] = "21:11"  # a 90-minute dinner

    res = _post("stop/1/alternatives?kind=meal", payload, KindProvider())

    assert all(_dwell_of(stop) == 90 for stop in res.json())


def test_swap_by_kind_works_where_the_stops_own_type_is_unknown() -> None:
    payload = _quest_payload()
    payload["stops"][1]["category"] = "attraction"
    payload["stops"][1]["place"]["types"] = ["point_of_interest"]

    res = _post("stop/1/alternatives?kind=walk", payload, KindProvider())

    assert res.status_code == 200
    assert res.json()


def test_unknown_kind_is_rejected_before_any_search() -> None:
    provider = KindProvider()
    res = _post("stop/1/alternatives?kind=casino", _quest_payload(), provider)

    assert res.status_code == 422
    assert provider.nearby_types == []


def test_nothing_of_that_kind_nearby_is_an_empty_list() -> None:
    res = _post("stop/1/alternatives?kind=bowling", _quest_payload(), KindProvider(empty=True))

    assert res.status_code == 200
    assert res.json() == []


# ── Films ──────────────────────────────────────────────────────────────────────


def _payload_with_middle_stop(category: str, types: list[str], end: str) -> dict:
    """The middle stop (it starts at 19:41) as something else, ending at `end`."""
    payload = _quest_payload()
    stop = payload["stops"][1]
    stop["category"] = category
    stop["place"]["types"] = types
    stop["time_block_end"] = end
    return payload


@pytest.mark.parametrize(
    ("category", "types", "end", "expected"),
    [
        ("restaurant", ["restaurant"], "20:41", FILM_MINUTES),
        ("activity", ["bowling_alley"], "20:41", FILM_MINUTES),
        # A generated quest gives a film the activity hour; asking for a film fixes it.
        ("activity", ["movie_theater"], "20:41", FILM_MINUTES),
        ("activity", ["movie_theater"], "22:41", 180),
    ],
)
def test_swapping_to_a_film_gives_it_a_films_length(category, types, end, expected) -> None:
    payload = _payload_with_middle_stop(category, types, end)

    res = _post("stop/1/alternatives?kind=movie", payload, KindProvider())

    assert res.status_code == 200
    assert {_dwell_of(stop) for stop in res.json()} == {expected}


def test_swapping_a_film_for_another_activity_does_not_keep_the_films_length() -> None:
    payload = _payload_with_middle_stop("activity", ["movie_theater"], "22:11")

    res = _post("stop/1/alternatives?kind=bowling", payload, KindProvider())

    assert {_dwell_of(stop) for stop in res.json()} == {60}


def test_a_similar_swap_of_a_film_keeps_its_length_as_before() -> None:
    payload = _payload_with_middle_stop("activity", ["movie_theater"], "20:41")

    res = _post("stop/1/alternatives", payload, KindProvider())

    assert {_dwell_of(stop) for stop in res.json()} == {60}


def test_an_added_film_gets_a_films_length() -> None:
    res = _post("stop/1/additions?kind=movie", _quest_payload(), KindProvider())

    best = res.json()[0]
    assert _dwell_of(best) == FILM_MINUTES
    assert best["delta"]["time_change_minutes"] >= FILM_MINUTES


# ── Adding a stop ──────────────────────────────────────────────────────────────


def test_addition_is_searched_around_the_stop_before_it() -> None:
    provider = KindProvider()
    res = _post("stop/1/additions?kind=coffee", _quest_payload(), provider)

    assert res.status_code == 200
    assert provider.geocode_queries == ["0.001,0.0"]
    assert provider.nearby_types == ["cafe"]
    body = res.json()
    assert {s["place"]["provider_id"] for s in body} == {"cafe_a", "cafe_b"}
    best = body[0]
    # Starts after the stop it follows ends (20:41) plus the walk there.
    assert _minutes(best["time_block_start"]) > _minutes("20:41")
    assert _dwell_of(best) == 40
    assert best["kind"] == "coffee"
    assert best["travel_to_next_minutes"] is not None
    # Adding it makes the quest longer by at least the time spent there.
    assert best["delta"]["time_change_minutes"] >= 40
    assert best["delta"]["distance_change_meters"] >= 0


def test_addition_is_measured_against_the_hop_the_quest_has() -> None:
    payload = _quest_payload()
    payload["stops"][1]["travel_to_next_minutes"] = 25  # written by hand

    res = _post("stop/1/additions?kind=coffee", payload, KindProvider())

    best = res.json()[0]
    there = _minutes(best["time_block_start"]) - _minutes("20:41")
    onward = best["travel_to_next_minutes"]
    assert best["delta"]["time_change_minutes"] == there + 40 + onward - 25


def test_addition_after_the_last_stop_has_no_onward_leg() -> None:
    res = _post("stop/2/additions?kind=dessert", _quest_payload(), KindProvider())

    assert res.status_code == 200
    best = res.json()[0]
    assert best["travel_to_next_minutes"] is None
    assert best["travel_mode"] is None
    assert best["category"] == "other"
    assert _dwell_of(best) == 30


def test_addition_needs_a_kind() -> None:
    provider = KindProvider()
    res = _post("stop/1/additions", _quest_payload(), provider)

    assert res.status_code == 422
    assert provider.nearby_types == []


def test_addition_is_refused_on_a_full_quest_without_spending_a_search() -> None:
    payload = _quest_payload()
    extra = {**payload["stops"][-1], "place": {**payload["stops"][-1]["place"], "provider_id": "fourth"}}
    payload["stops"].append(extra)
    provider = KindProvider()

    res = _post("stop/1/additions?kind=coffee", payload, provider)

    assert res.status_code == 422
    assert provider.nearby_types == []


@pytest.mark.parametrize("index", [-1, 3])
def test_addition_after_a_stop_that_does_not_exist(index: int) -> None:
    res = _post(f"stop/{index}/additions?kind=coffee", _quest_payload(), KindProvider())

    assert res.status_code == 404


# ── Frontend mirrors ───────────────────────────────────────────────────────────


def test_frontend_offers_exactly_these_kinds_with_matching_types() -> None:
    source = (FRONTEND_SRC / "lib" / "stopKinds.ts").read_text()
    offered = dict(re.findall(r"key: '(\w+)',[^}]*?placeType: '(\w+)'", source, re.S))

    assert offered == {kind.value: search[0] for kind, search in STOP_KIND_SEARCHES.items()}


def test_frontend_gives_a_film_the_same_length() -> None:
    source = (FRONTEND_SRC / "lib" / "questBuild.ts").read_text()

    assert f"export const FILM_MINUTES = {FILM_MINUTES}\n" in source


def test_frontend_knows_every_distance_note_the_engine_writes() -> None:
    """The quest page drops these notes once the stop before has changed."""
    place_kwargs = dict(name="x", address="y", lat=0.0, lng=0.0, distance_meters=0, provider_id="p")

    # 700 m reads as an easy walk whether the walking limit is 800 m or more.
    notes = {
        _why(PlaceItem(**place_kwargs), CostEstimate.mid, dist).rstrip(".").lower()
        for dist in (100.0, 700.0, 5000.0)
    }
    source = (FRONTEND_SRC / "lib" / "questBuild.ts").read_text().lower()

    assert len(notes) == 3
    for note in notes:
        assert f"'{note}'" in source
