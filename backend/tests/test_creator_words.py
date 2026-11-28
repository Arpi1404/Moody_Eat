"""A creator's own intro and stop notes: limits, tidying and storage."""

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import models
from curated_quests import CURATED_CITIES
from main import app
from models import (
    CREATOR_INTRO_MAX,
    CREATOR_NOTE_MAX,
    NARRATIVE_MAX,
    STOP_NOTE_MAX,
    Quest,
    tidy_text,
)

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setenv("QUEST_STORE_BACKEND", "sqlite")
    monkeypatch.setenv("QUEST_DB_PATH", str(tmp_path / "quests.db"))
    monkeypatch.setattr(
        "rate_limit.get_settings",
        lambda: SimpleNamespace(rate_limit_enabled=False, rate_limit_per_minute=0),
    )


def _payload(*, intro=None, note=None, by_creator=False) -> dict:
    """A real curated quest as the frontend would post it."""
    data = CURATED_CITIES[0].quests[0].model_dump(mode="json")
    if intro is not None:
        data["narrative"] = intro
        if by_creator:
            data["narrative_by_creator"] = True
    if note is not None:
        data["stops"][0]["why_this_place"] = note
        if by_creator:
            data["stops"][0]["note_by_creator"] = True
    return data


def test_every_curated_quest_still_fits():
    quests = [q for city in CURATED_CITIES for q in city.quests]
    for quest in quests:
        Quest.model_validate_json(quest.model_dump_json())
    assert max(len(s.why_this_place) for q in quests for s in q.stops) <= STOP_NOTE_MAX
    assert max(len(q.narrative) for q in quests) <= NARRATIVE_MAX


@pytest.mark.parametrize(
    "field, limit",
    [("intro", CREATOR_INTRO_MAX), ("note", CREATOR_NOTE_MAX)],
)
def test_creator_text_is_held_to_the_creator_limit(field, limit):
    Quest.model_validate(_payload(**{field: "x" * limit}, by_creator=True))
    with pytest.raises(ValidationError):
        Quest.model_validate(_payload(**{field: "x" * (limit + 1)}, by_creator=True))


@pytest.mark.parametrize(
    "field, limit",
    [("intro", NARRATIVE_MAX), ("note", STOP_NOTE_MAX)],
)
def test_text_without_the_marker_is_held_to_the_ceiling(field, limit):
    # Leaving the marker out buys room up to the ceiling and no further.
    Quest.model_validate(_payload(**{field: "x" * limit}))
    with pytest.raises(ValidationError):
        Quest.model_validate(_payload(**{field: "x" * (limit + 1)}))


def test_text_becomes_one_clean_line():
    messy = "  Go\r\n\r\nupstairs.\t\u2028Ask\u202e for\u0000 the   window  "
    quest = Quest.model_validate(_payload(intro=messy, note=messy, by_creator=True))
    expected = "Go upstairs. Ask for the window"
    assert quest.narrative == expected
    assert quest.stops[0].why_this_place == expected


@pytest.mark.parametrize("hidden", ["\u200b", "\u200c", "\u200d", "\u2060", "\ufeff"])
def test_zero_width_characters_are_removed(hidden):
    # Removed, not turned into spaces: the word they were hiding in is whole.
    assert tidy_text(f"ex{hidden}ample.com{hidden} {hidden}now") == "example.com now"
    assert tidy_text(hidden * 3) == ""
    # Beside only one emoji, a joiner joins nothing.
    assert tidy_text(f"\U0001F525{hidden} hot{hidden}\U0001F525") == "\U0001F525 hot\U0001F525"


@pytest.mark.parametrize(
    "emoji",
    [
        "\U0001F468\u200d\U0001F469\u200d\U0001F467",  # family
        "\U0001F3F3\ufe0f\u200d\U0001F308",  # rainbow flag
        "\U0001F468\U0001F3FD\u200d\U0001F4BB",  # with a skin tone
        "\u2764\ufe0f\u200d\U0001F525",  # heart on fire
    ],
)
def test_emoji_made_of_joined_parts_stay_whole(emoji):
    assert tidy_text(f"For {emoji} only") == f"For {emoji} only"


def test_the_markers_are_optional():
    data = _payload()
    quest = Quest.model_validate(data)
    assert quest.narrative_by_creator is None
    assert quest.stops[0].note_by_creator is None


def test_quests_without_creator_words_are_stored_without_the_markers():
    # The stored form of every other quest is unchanged, so sharing one that
    # was shared before still returns the same link.
    sent = _payload()
    sent["narrative_by_creator"] = None
    sent["stops"][0]["note_by_creator"] = False
    with TestClient(app) as client:
        short_id = client.post("/api/quest/store", json=sent).json()["short_id"]
        back = client.get(f"/api/quest/stored/{short_id}").json()
    assert "narrative_by_creator" not in back
    assert all("note_by_creator" not in stop for stop in back["stops"])
    assert "note_by_creator" not in Quest.model_validate(_payload()).model_dump_json()


def test_a_shared_link_keeps_the_words_and_markers():
    sent = _payload(intro="My intro.", note="Sit upstairs.", by_creator=True)
    with TestClient(app) as client:
        stored = client.post("/api/quest/store", json=sent)
        assert stored.status_code == 200
        back = client.get(f"/api/quest/stored/{stored.json()['short_id']}").json()
    assert back["narrative"] == "My intro."
    assert back["narrative_by_creator"] is True
    assert back["stops"][0]["why_this_place"] == "Sit upstairs."
    assert back["stops"][0]["note_by_creator"] is True


def test_an_overlong_creator_note_cannot_be_stored():
    sent = _payload(note="x" * (CREATOR_NOTE_MAX + 1), by_creator=True)
    with TestClient(app) as client:
        assert client.post("/api/quest/store", json=sent).status_code == 422


async def test_an_overlong_model_written_intro_falls_back(monkeypatch):
    from services import place_blurbs_service as blurbs

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *args, **kwargs):
            return SimpleNamespace(
                is_success=True,
                status_code=200,
                json=lambda: {"choices": [{"message": {"content": "y" * (NARRATIVE_MAX + 1)}}]},
            )

    monkeypatch.setattr(
        blurbs,
        "configured_text_model",
        lambda: blurbs.TextModel("https://model.test/v1/chat/completions", "m", "k" * 20),
    )
    monkeypatch.setattr(blurbs.httpx, "AsyncClient", _Client)
    text = await blurbs.generate_quest_narrative(
        "Indiranagar", "date", "mid", 2, [{"name": "Toit", "category": "bar", "why": "w"}]
    )
    assert len(text) <= NARRATIVE_MAX
    assert "Toit" in text


def test_the_frontend_uses_the_same_limits():
    source = (_FRONTEND / "lib" / "creatorText.ts").read_text()
    found = dict(re.findall(r"export const (CREATOR_\w+_MAX) = (\d+)", source))
    assert found == {
        "CREATOR_NOTE_MAX": str(models.CREATOR_NOTE_MAX),
        "CREATOR_INTRO_MAX": str(models.CREATOR_INTRO_MAX),
    }
