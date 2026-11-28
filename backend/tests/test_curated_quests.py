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
from models import AUDIENCE_LINE_MAX, ClosedDay, Occasion, Quest

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


# ── Closed days ──

# What a check against Google found on 28 Nov 2026. `verify_curated` is what
# tells when this stops being true.
CLOSED_DAYS = {
    "Lalbagh Light, Food Street Night": [("monday", "MTR (Mavalli Tiffin Rooms)")],
    "Church Street, One Book Each": [("monday", "Bar Spirit Forward")],
    "Cubbon Park, Then a Bookshop": [
        ("monday", "Cubbon Park"),
        ("monday", "Champaca Bookstore"),
    ],
    "Basavanagudi: Bull Temple to Butter Dosa": [("friday", "Vidyarthi Bhavan")],
    "Aravali Trails, Then Cameras": [("monday", "Museo Camera")],
}


def _quest(title: str) -> Quest:
    return next(q for c in CURATED_CITIES for q in c.quests if q.title == title)


def test_the_quests_that_do_not_work_every_day_say_which_stop_and_when() -> None:
    declared = {
        q.title: [(e.day, q.stops[e.stop_index].place.name) for e in q.closed_days]
        for c in CURATED_CITIES
        for q in c.quests
        if q.closed_days
    }
    assert declared == CLOSED_DAYS


def test_closed_days_are_served_and_left_out_when_there_are_none() -> None:
    with TestClient(app) as c:
        body = c.get("/api/quests/curated", params={"city": "bangalore"}).json()

    by_title = {q["title"]: q for q in body}
    lalbagh = _quest("Lalbagh Light, Food Street Night")
    assert by_title[lalbagh.title]["closed_days"] == [
        {"day": "monday", "stop_index": 1, "place_id": lalbagh.stops[1].place.provider_id}
    ]
    assert "closed_days" not in by_title["Koramangala: Burgers, Locked Rooms, Beer"]


def _rebuilt(quest: Quest, **changes) -> Quest:
    """The quest as it comes back from a browser."""
    data = quest.model_dump(mode="json")
    data.update(changes)
    return Quest.model_validate(data)


def test_a_quest_with_no_closed_days_serialises_as_before() -> None:
    quest = _quest("Koramangala: Burgers, Locked Rooms, Beer")
    assert "closed_days" not in quest.model_dump(mode="json")
    assert "closed_days" not in _rebuilt(quest, closed_days=[]).model_dump_json()


def test_an_unknown_weekday_is_refused() -> None:
    with pytest.raises(ValueError):
        ClosedDay(day="funday", stop_index=0)


def test_a_written_entry_must_name_a_stop_that_exists() -> None:
    quest = _quest("Lalbagh Light, Food Street Night")
    with pytest.raises(ValueError, match="names stop 3"):
        _rebuilt(quest, closed_days=[{"day": "monday", "stop_index": 3}])


def test_a_closed_day_stays_with_its_place_when_stops_move() -> None:
    quest = _quest("Lalbagh Light, Food Street Night")
    stops = quest.model_dump(mode="json")["stops"]
    moved = _rebuilt(quest, stops=[stops[1], stops[0], stops[2]])
    assert [(e.day, e.stop_index) for e in moved.closed_days] == [("monday", 0)]


@pytest.mark.parametrize("keep", [[0, 2], [0]], ids=["removed", "index now out of range"])
def test_a_closed_day_goes_with_its_place_instead_of_refusing_the_quest(keep) -> None:
    quest = _quest("Lalbagh Light, Food Street Night")
    stops = quest.model_dump(mode="json")["stops"]
    edited = _rebuilt(quest, stops=[stops[i] for i in keep])
    assert edited.closed_days is None


# ── What a catalogue card says ──


def test_every_quest_says_who_it_is_for_in_one_short_line_of_its_own() -> None:
    lines = [q.audience_line for c in CURATED_CITIES for q in c.quests]
    assert all(lines)
    assert all(len(line) <= AUDIENCE_LINE_MAX for line in lines)
    assert len(set(lines)) == len(lines)


def test_a_chosen_lead_photo_names_one_of_the_quests_stops() -> None:
    chosen = {
        q.title: q.stops[q.photo_stop.stop_index].place.name
        for c in CURATED_CITIES
        for q in c.quests
        if q.photo_stop
    }
    assert chosen == {"Jubilee Hills, Slow Burn": "Olive Bistro & Bar"}


def test_the_card_fields_are_left_out_when_unset() -> None:
    quest = _quest("HITEC City Game Night")
    assert "photo_stop" not in quest.model_dump(mode="json")
    bare = _rebuilt(quest, audience_line=None)
    assert "audience_line" not in bare.model_dump_json()


def test_a_lead_photo_follows_its_stop_and_goes_with_it() -> None:
    quest = _quest("Jubilee Hills, Slow Burn")
    stops = quest.model_dump(mode="json")["stops"]
    moved = _rebuilt(quest, stops=[stops[1], stops[0], stops[2]])
    assert moved.photo_stop.stop_index == 0
    assert _rebuilt(quest, stops=[stops[0]]).photo_stop is None
    with pytest.raises(ValueError, match="photo_stop names stop 5"):
        _rebuilt(quest, photo_stop={"stop_index": 5})


def test_an_overlong_audience_line_is_refused() -> None:
    with pytest.raises(ValueError):
        _rebuilt(_quest("HITEC City Game Night"), audience_line="x" * (AUDIENCE_LINE_MAX + 1))


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
