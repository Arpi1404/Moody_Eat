"""Tests for the shared-quest store (short links + view counts)."""

import re
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Point the store at a throwaway SQLite file per test."""
    monkeypatch.setenv("QUEST_DB_PATH", str(tmp_path / "quests.db"))


@pytest.fixture(autouse=True)
def no_rate_limit(monkeypatch):
    """The suite shares one limiter keyed on the test client IP; a burst of
    store calls here must not eat the budget of other tests (or vice versa)."""
    monkeypatch.setattr(
        "rate_limit.get_settings",
        lambda: SimpleNamespace(rate_limit_enabled=False, rate_limit_per_minute=0),
    )


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


def _quest_payload(title: str = "Old City Crawl") -> dict:
    return {
        "id": "11111111-1111-4111-8111-111111111111",
        "title": title,
        "occasion": "friends",
        "stops": [
            {
                "place": {
                    "name": "Nimrah Cafe",
                    "address": "Charminar Road",
                    "lat": 17.36,
                    "lng": 78.47,
                    "distance_meters": 0,
                    "rating": 4.4,
                    "user_ratings_total": 9000,
                    "types": ["cafe"],
                    "provider_id": "nimrah",
                },
                "category": "cafe",
                "time_block_start": "17:30",
                "time_block_end": "18:15",
                "travel_to_next_minutes": 10,
                "travel_mode": "walking",
                "why_this_place": "Irani chai institution.",
            },
            {
                "place": {
                    "name": "Charminar",
                    "address": "Old City",
                    "lat": 17.3616,
                    "lng": 78.4747,
                    "distance_meters": 400,
                    "rating": 4.5,
                    "user_ratings_total": 120000,
                    "types": ["tourist_attraction"],
                    "provider_id": "charminar",
                },
                "category": "attraction",
                "time_block_start": "18:25",
                "time_block_end": "19:25",
                "travel_to_next_minutes": None,
                "travel_mode": None,
                "why_this_place": "The landmark itself.",
            },
        ],
        "total_duration_minutes": 115,
        "total_cost_estimate": "cheap",
        "narrative": "Chai first, then the monument at golden hour.",
        "created_at": "2026-07-14T12:00:00",
    }


def test_store_and_fetch_roundtrip(client: TestClient) -> None:
    res = client.post("/api/quest/store", json=_quest_payload())
    assert res.status_code == 200
    body = res.json()
    assert re.fullmatch(r"[23456789abcdefghjkmnpqrstuvwxyz]{8}", body["short_id"])
    assert body["path"] == f"/q/{body['short_id']}"

    fetched = client.get(f"/api/quest/stored/{body['short_id']}")
    assert fetched.status_code == 200
    quest = fetched.json()
    assert quest["title"] == "Old City Crawl"
    assert [s["place"]["name"] for s in quest["stops"]] == ["Nimrah Cafe", "Charminar"]


def test_store_is_idempotent_for_identical_content(client: TestClient) -> None:
    first = client.post("/api/quest/store", json=_quest_payload()).json()
    second = client.post("/api/quest/store", json=_quest_payload()).json()
    assert first["short_id"] == second["short_id"]


def test_store_gives_new_id_when_content_changes(client: TestClient) -> None:
    first = client.post("/api/quest/store", json=_quest_payload()).json()
    renamed = client.post("/api/quest/store", json=_quest_payload(title="Priya's Crawl")).json()
    assert first["short_id"] != renamed["short_id"]


def test_store_drops_unknown_fields(client: TestClient) -> None:
    payload = _quest_payload()
    payload["evil_extra"] = "x" * 500
    short_id = client.post("/api/quest/store", json=payload).json()["short_id"]
    fetched = client.get(f"/api/quest/stored/{short_id}").json()
    assert "evil_extra" not in fetched


def test_fetch_unknown_short_id_is_404(client: TestClient) -> None:
    res = client.get("/api/quest/stored/zzzzzzzz")
    assert res.status_code == 404
    assert "message" in res.json()["detail"]


def test_views_count_humans_but_not_crawlers(client: TestClient) -> None:
    short_id = client.post("/api/quest/store", json=_quest_payload()).json()["short_id"]

    stats = client.get(f"/api/quest/stored/{short_id}/stats").json()
    assert stats["views"] == 0

    client.get(f"/api/quest/stored/{short_id}")
    client.get(f"/api/quest/stored/{short_id}")
    client.get(f"/api/quest/stored/{short_id}?count_view=false")

    stats = client.get(f"/api/quest/stored/{short_id}/stats").json()
    assert stats["views"] == 2
    assert stats["short_id"] == short_id
    assert stats["created_at"]


def test_store_rejects_invalid_payload(client: TestClient) -> None:
    res = client.post("/api/quest/store", json={"title": "not a quest"})
    assert res.status_code == 422


def test_store_rejects_oversized_payload(client: TestClient) -> None:
    payload = _quest_payload()
    payload["narrative"] = "x" * 200_000
    res = client.post("/api/quest/store", json=payload)
    assert res.status_code == 413


def test_store_rejects_too_many_stops(client: TestClient) -> None:
    payload = _quest_payload()
    payload["stops"] = payload["stops"] * 20
    res = client.post("/api/quest/store", json=payload)
    assert res.status_code == 422


def test_creator_name_survives_store_roundtrip(client: TestClient) -> None:
    payload = _quest_payload(title="Priya's Old City Crawl")
    payload["created_by"] = "Priya"
    short_id = client.post("/api/quest/store", json=payload).json()["short_id"]
    fetched = client.get(f"/api/quest/stored/{short_id}").json()
    assert fetched["created_by"] == "Priya"


def test_store_rejects_over_long_creator_name(client: TestClient) -> None:
    payload = _quest_payload()
    payload["created_by"] = "x" * 61
    res = client.post("/api/quest/store", json=payload)
    assert res.status_code == 422
