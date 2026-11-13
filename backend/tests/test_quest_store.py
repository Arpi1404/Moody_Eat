"""Tests for the shared-quest store (short links + view counts)."""

import re
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from main import app


class _FakeSnapshot:
    def __init__(self, data: dict | None) -> None:
        self.exists = data is not None
        self._data = data

    def to_dict(self) -> dict | None:
        return dict(self._data) if self._data is not None else None


class _FakeDocument:
    """Just the DocumentReference calls quest_store makes, with Firestore's
    create/update error semantics."""

    def __init__(self, docs: dict, key: tuple[str, str]) -> None:
        self._docs = docs
        self._key = key

    def get(self) -> _FakeSnapshot:
        return _FakeSnapshot(self._docs.get(self._key))

    def create(self, data: dict) -> None:
        from google.api_core.exceptions import AlreadyExists

        if self._key in self._docs:
            raise AlreadyExists("exists")
        self._docs[self._key] = dict(data)

    def update(self, data: dict) -> None:
        from google.api_core.exceptions import NotFound
        from google.cloud.firestore_v1.transforms import Increment

        if self._key not in self._docs:
            raise NotFound("missing")
        doc = self._docs[self._key]
        for field, value in data.items():
            doc[field] = doc.get(field, 0) + value.value if isinstance(value, Increment) else value

    def delete(self) -> None:
        self._docs.pop(self._key, None)


class _FakeFirestore:
    def __init__(self) -> None:
        self.docs: dict = {}

    def collection(self, name: str):
        return SimpleNamespace(document=lambda doc_id: _FakeDocument(self.docs, (name, doc_id)))


@pytest.fixture(autouse=True, params=["sqlite", "firestore"])
def isolated_db(request, tmp_path, monkeypatch):
    """Run every test against a throwaway SQLite file and against an
    in-memory stand-in for the Firestore client."""
    monkeypatch.setenv("QUEST_STORE_BACKEND", request.param)
    monkeypatch.setenv("QUEST_DB_PATH", str(tmp_path / "quests.db"))
    fake = _FakeFirestore()
    monkeypatch.setattr("quest_store.firestore_client", lambda: fake)
    return fake


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


def test_firestore_concurrent_same_content_keeps_one_link(isolated_db, monkeypatch) -> None:
    """If another request stores identical content between our hash check and
    our hash create, we return their short id and drop our duplicate doc."""
    import quest_store
    from models import Quest

    if quest_store._backend() != "firestore":
        pytest.skip("firestore-only race")
    quest = Quest.model_validate(_quest_payload())
    _, content_hash = quest_store._canonical(quest)
    fake = isolated_db

    real_new_id = quest_store._new_short_id

    def racing_new_id() -> str:
        # Simulate the other request winning the hash doc mid-flight.
        fake.docs[("shared_quest_hashes", content_hash)] = {"short_id": "theirs22"}
        fake.docs[("shared_quests", "theirs22")] = {"quest_json": "{}", "created_at": "x", "views": 0}
        return real_new_id()

    monkeypatch.setattr(quest_store, "_new_short_id", racing_new_id)
    assert quest_store.store_quest(quest) == "theirs22"
    assert [k for k in fake.docs if k[0] == "shared_quests"] == [("shared_quests", "theirs22")]
