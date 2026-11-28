"""A generated quest says which day it is for, and why its start moved."""

from datetime import datetime, time, timedelta

from fastapi.testclient import TestClient

from curated_quests import CURATED_CITIES
from main import app
from models import Occasion
from tests.test_start_time import TODAY, Pools, _clock, _open_city, _req, _run


def _payload(**extra) -> dict:
    data = CURATED_CITIES[0].quests[0].model_dump(mode="json")
    data.update(extra)
    return data


def test_a_quest_for_a_chosen_day_carries_it() -> None:
    day = TODAY + timedelta(days=3)
    quest = _run(Pools(_open_city()), _req(Occasion.solo, stops=1, start_date=day, start_time="10:00"))
    assert quest.outing_date == day
    assert quest.start_note is None
    assert f'"outing_date":"{day.isoformat()}"' in quest.model_dump_json()
    assert "start_note" not in quest.model_dump_json()


def test_without_a_day_or_a_clock_the_quest_names_no_day() -> None:
    quest = _run(Pools(_open_city()), _req(Occasion.solo, stops=1))
    assert quest.outing_date is None
    assert "outing_date" not in quest.model_dump_json()


def test_with_the_places_clock_today_is_named(monkeypatch) -> None:
    _clock(monkeypatch, datetime.combine(TODAY, time(3, 0)))  # 08:30 there
    quest = _run(Pools(_open_city()), _req(Occasion.solo, stops=1))
    assert quest.outing_date == TODAY


def test_a_moved_start_says_to_what_and_why(monkeypatch) -> None:
    _clock(monkeypatch, datetime.combine(TODAY, time(12, 5)))  # 17:35 there
    quest = _run(Pools(_open_city()), _req(Occasion.solo, stops=2, start_date=TODAY, start_time="10:00"))
    assert quest.start_note == (
        "It was already past 10 am in Somewhere, so this plan starts at 5:45 pm."
    )
    assert quest.outing_date == TODAY


def test_the_day_and_note_survive_the_store_route() -> None:
    sent = _payload(outing_date="2026-12-03", start_note="It was already past 6 pm, so this plan starts at 7:15 pm.")
    with TestClient(app) as client:
        stored = client.post("/api/quest/store", json=sent)
        assert stored.status_code == 200
        back = client.get(f"/api/quest/stored/{stored.json()['short_id']}").json()
    assert back["outing_date"] == "2026-12-03"
    assert back["start_note"].startswith("It was already past 6 pm")


def test_a_quest_without_them_is_stored_exactly_as_before() -> None:
    # Same stored form, so sharing a quest shared before still finds its link.
    sent = _payload(outing_date=None, start_note=None)
    with TestClient(app) as client:
        first = client.post("/api/quest/store", json=_payload()).json()["short_id"]
        again = client.post("/api/quest/store", json=sent).json()["short_id"]
        back = client.get(f"/api/quest/stored/{first}").json()
    assert first == again
    assert "outing_date" not in back and "start_note" not in back


def test_catalogue_quests_name_no_day() -> None:
    for city in CURATED_CITIES:
        for quest in city.quests:
            assert quest.outing_date is None
            assert "outing_date" not in quest.model_dump_json()
