"""Tests for the swap log: what a confirmed stop swap leaves behind."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import swap_log
from main import app
from scripts.swap_report import summarize

# Real-shaped Google place ids (27 URL-safe characters).
TRUFFLES = "ChIJ-3cMy7oWrjsRu8up6eYKXaI"
CHIANTI = "ChIJYyvzFKUWrjsRQxHn48rD5T8"
MAFFEI = "ChIJAQhx3hMVrjsR9xKKAqbages"


class _FakeSwapCollection:
    """The two CollectionReference calls swap_log makes."""

    def __init__(self, docs: list[dict]) -> None:
        self._docs = docs

    def add(self, data: dict) -> None:
        self._docs.append(dict(data))

    def stream(self):
        return [SimpleNamespace(to_dict=lambda doc=doc: dict(doc)) for doc in self._docs]


class _FakeFirestore:
    def __init__(self) -> None:
        self.collections: dict[str, list[dict]] = {}

    def collection(self, name: str) -> _FakeSwapCollection:
        return _FakeSwapCollection(self.collections.setdefault(name, []))


@pytest.fixture(autouse=True, params=["sqlite", "firestore"])
def isolated_store(request, tmp_path, monkeypatch):
    """Every test runs against a throwaway SQLite file and against an
    in-memory stand-in for Firestore."""
    monkeypatch.setenv("QUEST_STORE_BACKEND", request.param)
    monkeypatch.setenv("QUEST_DB_PATH", str(tmp_path / "quests.db"))
    fake = _FakeFirestore()
    monkeypatch.setattr("quest_store.firestore_client", lambda: fake)
    return fake


@pytest.fixture(autouse=True)
def no_rate_limit(monkeypatch):
    monkeypatch.setattr(
        "rate_limit.get_settings",
        lambda: SimpleNamespace(rate_limit_enabled=False, rate_limit_per_minute=0),
    )


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


def _event(**overrides) -> dict:
    event = {
        "from_place_id": TRUFFLES,
        "to_place_id": CHIANTI,
        "shown_place_ids": [MAFFEI, CHIANTI],
        "occasion": "date",
        "category": "restaurant",
        "budget": "mid",
        "stop_index": 0,
        "stop_count": 3,
        "slot_start": "19:30:00",
        "quest_origin": "generated",
    }
    event.update(overrides)
    return event


def test_swap_is_recorded(client: TestClient) -> None:
    res = client.post("/api/quest/swap-log", json=_event())
    assert res.status_code == 204
    assert res.content == b""

    [swap] = swap_log.load_swaps()
    assert swap["from_place_id"] == TRUFFLES
    assert swap["to_place_id"] == CHIANTI
    assert swap["shown_place_ids"] == [MAFFEI, CHIANTI]
    # Chianti was the second option offered.
    assert swap["chosen_rank"] == 1
    assert swap["occasion"] == "date"
    assert swap["category"] == "restaurant"
    assert swap["budget"] == "mid"
    assert (swap["stop_index"], swap["stop_count"]) == (0, 3)
    assert swap["slot_start"] == "19:30"
    assert swap["quest_origin"] == "generated"
    assert swap["v"] == swap_log.SCHEMA_VERSION
    assert swap["created_at"]


def test_nothing_about_the_person_or_quest_is_stored(client: TestClient) -> None:
    """The stored record is exactly this set of fields. Sending a quest id,
    coordinates or a name must not get them stored; adding a field to the
    record should be a deliberate change to this test."""
    payload = _event(
        quest_id="11111111-1111-4111-8111-111111111111",
        lat=12.9716,
        lng=77.5946,
        created_by="Priya",
        note="our anniversary",
    )
    assert client.post("/api/quest/swap-log", json=payload).status_code == 204

    [swap] = swap_log.load_swaps()
    assert set(swap) == {
        "v",
        "created_at",
        "from_place_id",
        "to_place_id",
        "shown_place_ids",
        "chosen_rank",
        "occasion",
        "category",
        "budget",
        "stop_index",
        "stop_count",
        "slot_start",
        "quest_origin",
    }


def test_swaps_accumulate_in_order(client: TestClient) -> None:
    client.post("/api/quest/swap-log", json=_event())
    client.post("/api/quest/swap-log", json=_event(to_place_id=MAFFEI, occasion="friends"))
    swaps = swap_log.load_swaps()
    assert [s["to_place_id"] for s in swaps] == [CHIANTI, MAFFEI]


def test_chosen_rank_is_unknown_when_choice_was_not_in_the_list(client: TestClient) -> None:
    client.post("/api/quest/swap-log", json=_event(shown_place_ids=[MAFFEI]))
    assert swap_log.load_swaps()[0]["chosen_rank"] is None


def test_optional_fields_can_be_left_out(client: TestClient) -> None:
    payload = _event()
    del payload["shown_place_ids"]
    del payload["quest_origin"]
    assert client.post("/api/quest/swap-log", json=payload).status_code == 204
    [swap] = swap_log.load_swaps()
    assert swap["shown_place_ids"] == []
    assert swap["quest_origin"] is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"to_place_id": TRUFFLES},  # swapped for itself
        {"from_place_id": "nimrah"},  # not a place id
        {"to_place_id": "ChIJ bad id with spaces!!"},
        {"shown_place_ids": [CHIANTI] * 13},  # more options than the sheet shows
        {"shown_place_ids": ["<script>"]},
        {"occasion": "wedding"},
        {"category": "spaceship"},
        {"budget": "free"},
        {"stop_index": 3},  # outside a 3-stop quest
        {"stop_count": 0},
        {"slot_start": "25:99"},
        {"quest_origin": "stolen"},
    ],
)
def test_invalid_events_are_rejected_and_not_stored(client: TestClient, overrides: dict) -> None:
    res = client.post("/api/quest/swap-log", json=_event(**overrides))
    assert res.status_code == 422
    assert swap_log.load_swaps() == []


def test_oversized_event_is_rejected(client: TestClient) -> None:
    payload = _event(padding="x" * 20_000)
    res = client.post("/api/quest/swap-log", json=payload)
    assert res.status_code == 413
    assert swap_log.load_swaps() == []


def test_store_failure_is_a_503_not_a_crash(client: TestClient, monkeypatch) -> None:
    def broken(_event) -> None:
        raise RuntimeError("firestore is down")

    monkeypatch.setattr("routes.record_swap", broken)
    res = client.post("/api/quest/swap-log", json=_event())
    assert res.status_code == 503
    assert "message" in res.json()["detail"]


def test_swap_log_has_its_own_small_allowance(client: TestClient, monkeypatch) -> None:
    """A script posting swaps is cut off after 20 a minute, and that does not
    spend the caller's allowance for searches."""
    import rate_limit

    monkeypatch.setattr(
        "rate_limit.get_settings",
        lambda: SimpleNamespace(
            rate_limit_enabled=True,
            rate_limit_per_minute=60,
            suggest_rate_limit_per_minute=120,
        ),
    )
    monkeypatch.setattr(rate_limit, "_limiters", {})

    statuses = [client.post("/api/quest/swap-log", json=_event()).status_code for _ in range(22)]
    assert statuses[:20] == [204] * 20
    assert statuses[20:] == [429, 429]
    assert len(swap_log.load_swaps()) == 20

    # The search allowance is untouched: storing a quest is still allowed
    # (it fails validation, which is past the rate limiter).
    assert client.post("/api/quest/store", json={"title": "not a quest"}).status_code == 422


def test_report_counts_replacements() -> None:
    swaps = [
        {"from_place_id": TRUFFLES, "to_place_id": CHIANTI, "occasion": "date", "quest_origin": "generated"},
        {"from_place_id": TRUFFLES, "to_place_id": CHIANTI, "occasion": "date", "quest_origin": None},
        {"from_place_id": TRUFFLES, "to_place_id": MAFFEI, "occasion": "friends", "quest_origin": "curated"},
    ]
    everything = summarize(swaps)
    assert everything["total"] == 3
    assert everything["replaced"][TRUFFLES] == 3
    assert everything["pairs"][(TRUFFLES, CHIANTI)] == 2
    assert everything["by_origin"] == {"generated": 1, "unknown": 1, "curated": 1}

    dates = summarize(swaps, occasion="date")
    assert dates["total"] == 2
    assert dates["chosen"] == {CHIANTI: 2}


# ── Quest origin ─────────────────────────────────────────────────────────────


def test_curated_quests_say_they_are_curated(client: TestClient) -> None:
    quests = client.get("/api/quests/curated?city=hyderabad").json()
    assert quests and {q["origin"] for q in quests} == {"curated"}
    one = client.get(f"/api/quests/curated/{quests[0]['id']}").json()
    assert one["origin"] == "curated"


def test_quests_without_an_origin_still_validate() -> None:
    """Share links made before the field existed carry no origin."""
    from models import Quest

    quest = Quest.model_validate(
        {
            "title": "Old link",
            "occasion": "solo",
            "stops": [],
            "total_duration_minutes": 0,
            "total_cost_estimate": "cheap",
            "narrative": "x",
        }
    )
    assert quest.origin is None
