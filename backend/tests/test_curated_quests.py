"""Curated quests: the city registry, its endpoints, and content sanity checks.

The content checks need no network — they catch the mistakes a hand-written
quest can carry (a repeated venue, a schedule that doesn't add up, a stop in
the wrong city). Whether a venue is still open and well rated is the job of
`scripts/verify_curated.py`, which asks Google.
"""

import math
import uuid
from collections import Counter
from datetime import time

import pytest
from fastapi.testclient import TestClient

from curated_quests import (
    CURATED_CITIES,
    QUESTS_PER_CITY,
    CuratedCity,
    find_city,
    find_quest,
)
from main import app
from models import Occasion

EXPECTED_MIX = {Occasion.date: 2, Occasion.friends: 2, Occasion.solo: 1, Occasion.family: 1}
MAX_KM_FROM_CENTRE = 40
MAX_WAIT_MINUTES = 30

per_city = pytest.mark.parametrize("city", CURATED_CITIES, ids=lambda c: c.key)


def _km(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> float:
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lng - a_lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute


# ── Registry ──


def test_three_cities_in_toggle_order() -> None:
    assert [c.key for c in CURATED_CITIES] == ["hyderabad", "bangalore", "gurgaon"]


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("Hyderabad", "hyderabad"),
        ("  bengaluru ", "bangalore"),
        ("GURUGRAM", "gurgaon"),
        ("Secunderabad", "hyderabad"),
    ],
)
def test_find_city_knows_keys_and_other_names(name: str, key: str) -> None:
    city = find_city(name)
    assert city is not None and city.key == key


def test_find_city_returns_none_elsewhere() -> None:
    assert find_city("Mumbai") is None


def test_quest_ids_are_unique_across_cities() -> None:
    ids = [q.id for c in CURATED_CITIES for q in c.quests]
    assert len(ids) == len(set(ids))
    assert find_quest(ids[0]) is CURATED_CITIES[0].quests[0]
    assert find_quest(uuid.uuid4()) is None


# ── Content ──


@per_city
def test_city_has_six_quests_in_the_agreed_mix(city: CuratedCity) -> None:
    assert len(city.quests) == QUESTS_PER_CITY
    assert Counter(q.occasion for q in city.quests) == EXPECTED_MIX
    titles = [q.title for q in city.quests]
    assert len(titles) == len(set(titles))


@per_city
def test_no_venue_appears_twice_and_every_id_is_real(city: CuratedCity) -> None:
    ids = [s.place.provider_id for q in city.quests for s in q.stops]
    repeated = [pid for pid, n in Counter(ids).items() if n > 1]
    assert not repeated
    for pid in ids:
        # Google Place IDs for venues start "ChIJ"; "Ek…" is a street address
        # and "pending:" / "curated-" are unresolved placeholders.
        assert pid.startswith("ChIJ"), pid


@per_city
def test_stops_are_in_town_and_well_rated(city: CuratedCity) -> None:
    for quest in city.quests:
        for s in quest.stops:
            away = _km(city.lat, city.lng, s.place.lat, s.place.lng)
            assert away <= MAX_KM_FROM_CENTRE, f"{s.place.name} is {away:.0f} km from {city.name}"
            assert s.place.rating is not None and s.place.rating >= 4.0, s.place.name
            assert len(s.why_this_place) >= 40, s.place.name


@per_city
def test_schedules_add_up(city: CuratedCity) -> None:
    for quest in city.quests:
        stops = quest.stops
        assert 2 <= len(stops) <= 4, quest.title
        assert len(quest.narrative) >= 120, quest.title

        for s in stops:
            assert _minutes(s.time_block_end) > _minutes(s.time_block_start), s.place.name

        for current, following in zip(stops, stops[1:]):
            assert current.travel_to_next_minutes, f"{current.place.name}: no travel time"
            assert current.travel_mode is not None
            arrives = _minutes(current.time_block_end) + current.travel_to_next_minutes
            wait = _minutes(following.time_block_start) - arrives
            assert 0 <= wait <= MAX_WAIT_MINUTES, (
                f"{quest.title}: {following.place.name} starts {wait} min after arrival"
            )

        assert stops[-1].travel_to_next_minutes is None, quest.title
        span = _minutes(stops[-1].time_block_end) - _minutes(stops[0].time_block_start)
        assert quest.total_duration_minutes == span, quest.title


# ── Endpoints ──


@pytest.mark.parametrize("name", ["Hyderabad", "bangalore", "Bengaluru", "gurugram"])
def test_curated_list_for_a_city(name: str) -> None:
    with TestClient(app) as c:
        res = c.get("/api/quests/curated", params={"city": name})

    assert res.status_code == 200
    body = res.json()
    assert len(body) == QUESTS_PER_CITY
    first = body[0]
    assert set(first) >= {
        "id",
        "title",
        "occasion",
        "stops",
        "total_duration_minutes",
        "total_cost_estimate",
        "narrative",
        "created_at",
    }
    assert "place" in first["stops"][0]
    assert "why_this_place" in first["stops"][0]


def test_curated_list_for_an_unknown_city_names_the_ones_we_have() -> None:
    with TestClient(app) as c:
        res = c.get("/api/quests/curated", params={"city": "Mumbai"})

    assert res.status_code == 404
    assert res.json()["detail"]["available_cities"] == ["hyderabad", "bangalore", "gurgaon"]


def test_curated_quest_by_id() -> None:
    quest = CURATED_CITIES[1].quests[0]
    with TestClient(app) as c:
        res = c.get(f"/api/quests/curated/{quest.id}")

    assert res.status_code == 200
    assert res.json()["title"] == quest.title


def test_curated_quest_by_unknown_id_is_a_404() -> None:
    with TestClient(app) as c:
        missing = c.get(f"/api/quests/curated/{uuid.uuid4()}")
        malformed = c.get("/api/quests/curated/not-a-uuid")

    assert missing.status_code == 404
    assert malformed.status_code == 422
