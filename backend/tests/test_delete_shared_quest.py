"""Taking a shared quest down, on both store backends."""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import quest_store
from curated_quests import CURATED_CITIES
from main import app
from models import Quest
from scripts.delete_shared_quest import main, parse_short_id
from tests.test_quest_store import _FakeFirestore


@pytest.fixture(autouse=True, params=["sqlite", "firestore"])
def isolated_store(request, tmp_path, monkeypatch):
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


def _quest(title: str = "Evening out") -> Quest:
    base = CURATED_CITIES[0].quests[0]
    return Quest.model_validate({**base.model_dump(), "title": title})


def test_a_deleted_quest_is_gone_from_the_api():
    short_id = quest_store.store_quest(_quest())
    assert quest_store.delete_quest(short_id) is True
    with TestClient(app) as client:
        assert client.get(f"/api/quest/stored/{short_id}").status_code == 404
        assert client.get(f"/api/quest/stored/{short_id}/stats").status_code == 404


def test_sharing_the_same_quest_again_gives_a_link_that_works():
    # A hash entry left behind would answer with the deleted id.
    quest = _quest()
    first = quest_store.store_quest(quest)
    quest_store.delete_quest(first)
    again = quest_store.store_quest(quest)
    assert again != first
    assert quest_store.fetch_quest(again, count_view=False) is not None


def test_other_quests_are_left_alone():
    doomed = quest_store.store_quest(_quest("Doomed"))
    kept = quest_store.store_quest(_quest("Kept"))
    quest_store.delete_quest(doomed)
    assert quest_store.fetch_quest(kept, count_view=False) is not None
    assert quest_store.store_quest(_quest("Kept")) == kept


def test_deleting_what_is_not_there():
    assert quest_store.delete_quest("abcd2345") is False


@pytest.mark.parametrize("answer, gone", [("y", True), ("YES", True), ("", False), ("n", False)])
def test_script_asks_before_deleting(monkeypatch, capsys, answer, gone):
    short_id = quest_store.store_quest(_quest("Rooftops"))
    monkeypatch.setattr("builtins.input", lambda prompt: answer)
    code = main([short_id])
    assert code == (0 if gone else 1)
    assert (quest_store.fetch_quest(short_id, count_view=False) is None) is gone
    shown = capsys.readouterr().out
    assert "Rooftops" in shown
    assert "Store: " in shown


def test_script_takes_a_link_and_can_skip_the_question(monkeypatch):
    short_id = quest_store.store_quest(_quest())
    monkeypatch.setattr("builtins.input", lambda prompt: pytest.fail("must not ask"))
    assert main([f"https://www.moodyeat.in/q/{short_id}?x=1", "--yes"]) == 0
    assert quest_store.fetch_quest(short_id, count_view=False) is None


def test_script_shows_the_words_without_terminal_escape_codes(monkeypatch, capsys):
    quest = _quest()
    raw = json.loads(quest.model_dump_json())
    raw["title"] = "Bad \u001b[2J title"
    short_id = quest_store.store_quest(Quest.model_validate(raw))
    monkeypatch.setattr("builtins.input", lambda prompt: "n")
    main([short_id])
    assert "\u001b" not in capsys.readouterr().out


def test_looking_before_deleting_counts_no_view(monkeypatch):
    short_id = quest_store.store_quest(_quest())
    monkeypatch.setattr("builtins.input", lambda prompt: "n")
    main([short_id])
    assert quest_store.fetch_quest(short_id, count_view=False).views == 0


def test_script_reports_a_missing_quest(capsys):
    assert main(["abcd2345", "--yes"]) == 1
    assert "No shared quest" in capsys.readouterr().err


@pytest.mark.parametrize("value", ["", "ab", "../etc", "ABCD2345", "https://x.test/quest/abc"])
def test_script_refuses_what_is_not_an_id(value):
    assert parse_short_id(value) is None
    assert main([value, "--yes"]) == 2


@pytest.mark.parametrize(
    "value",
    ["abcd2345", " abcd2345 ", "/q/abcd2345", "https://www.moodyeat.in/q/abcd2345/#top"],
)
def test_script_reads_ids_and_links(value):
    assert parse_short_id(value) == "abcd2345"
