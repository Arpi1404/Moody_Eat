"""The text model behind quest intros and blurbs, against a stubbed HTTP layer."""

from __future__ import annotations

import asyncio
import json
import logging

import httpx
import pytest

from config import get_settings
from models import NARRATIVE_MAX, PlaceBlurbIn, QuestGenerationRequest
from quest_generator import _display_location
from scripts import check_text_model
from services import place_blurbs_service as blurbs

URL = "https://model.test/v1/chat/completions"
NAME = "some-model"
KEY = "sk-test-9f8e7d6c5b4a39281706abcdef"
STOPS = [
    {"name": "Cafe One", "category": "cafe", "why": "Just a short walk away."},
    {"name": "Park Two", "category": "attraction", "why": "A solid local choice."},
]
PLACES = [PlaceBlurbIn(provider_id="p1", name="Cafe One", types=["cafe"])]


@pytest.fixture
def settings(monkeypatch):
    def _set(url: str = URL, name: str = NAME, key: str = KEY) -> None:
        monkeypatch.setenv("TEXT_MODEL_URL", url)
        monkeypatch.setenv("TEXT_MODEL_NAME", name)
        monkeypatch.setenv("TEXT_MODEL_API_KEY", key)
        get_settings.cache_clear()

    _set()
    return _set


@pytest.fixture
def provider(monkeypatch):
    """Answer every request with `respond`, and keep what was sent."""

    class Provider:
        def __init__(self) -> None:
            self.requests: list[httpx.Request] = []
            self.respond = lambda request: _answer("A fine evening.")

        async def handle(self, request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            result = self.respond(request)
            return await result if asyncio.iscoroutine(result) else result

        @property
        def prompt(self) -> str:
            return json.loads(self.requests[-1].content)["messages"][0]["content"]

    stub = Provider()
    real_client = httpx.AsyncClient

    def client(**kwargs):
        return real_client(transport=httpx.MockTransport(stub.handle), **kwargs)

    monkeypatch.setattr(blurbs.httpx, "AsyncClient", client)
    return stub


@pytest.fixture(autouse=True)
def logs(caplog):
    caplog.set_level(logging.DEBUG)
    yield caplog
    # Whatever happened, the key is in no log line.
    for record in caplog.records:
        assert KEY not in record.getMessage()
        assert KEY[:8] not in record.getMessage()


def _answer(content: object, finish: str = "stop") -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": content}, "finish_reason": finish}]},
    )


async def _narrative(location: str = "Old Town") -> str:
    return await blurbs.generate_quest_narrative(
        location, "date", "mid", 2, STOPS, day_part="evening"
    )


def _expected_fallback(location: str = "Old Town") -> str:
    return blurbs._fallback_narrative(
        location, "date", "mid", ["Cafe One", "Park Two"], "evening"
    )


def _fallback_lines(logs) -> list[str]:
    return [m for r in logs.records if "_fallback" in (m := r.getMessage())]


async def test_a_good_answer_is_used(settings, provider, logs):
    assert await _narrative() == "A fine evening."

    [request] = provider.requests
    assert str(request.url) == URL
    assert request.headers["authorization"] == f"Bearer {KEY}"
    body = json.loads(request.content)
    assert set(body) == {"model", "max_tokens", "messages"}
    assert body["model"] == NAME
    assert body["max_tokens"] == blurbs.NARRATIVE_MAX_TOKENS
    assert "in Old Town." in provider.prompt
    assert _fallback_lines(logs) == []


@pytest.mark.parametrize(
    "values",
    [{"url": ""}, {"name": ""}, {"key": ""}, {"key": "   "}],
    ids=["no address", "no model name", "no key", "blank key"],
)
async def test_a_missing_setting_sends_nothing(settings, provider, logs, values):
    settings(**values)

    assert await _narrative() == _expected_fallback()
    out = await blurbs.generate_place_blurbs(PLACES, "cozy", "mid", 2)

    assert out == {"p1": blurbs._fallback_blurb(PLACES[0], "cozy", "mid")}
    assert provider.requests == []
    assert _fallback_lines(logs) == []


async def test_the_old_key_setting_is_not_read(provider, monkeypatch):
    monkeypatch.setenv("OPENCODE_API_KEY", KEY)
    get_settings.cache_clear()
    assert await _narrative() == _expected_fallback()
    assert provider.requests == []


async def test_a_refusal_logs_the_status_and_the_providers_words(settings, provider, logs):
    provider.respond = lambda request: httpx.Response(
        400, json={"error": {"message": "Missing header x-session.\nTry again."}}
    )

    assert await _narrative() == _expected_fallback()

    [line] = _fallback_lines(logs)
    assert "narrative_fallback reason=http_status status=400" in line
    assert "Missing header x-session. Try again." in line
    assert "\n" not in line


async def test_a_long_error_is_cut_short(settings, provider, logs):
    provider.respond = lambda request: httpx.Response(503, text="busy " * 500)
    await _narrative()
    [line] = _fallback_lines(logs)
    assert "status=503" in line
    assert len(line) < blurbs._ERROR_SNIPPET_MAX + 100


@pytest.mark.parametrize(
    "message",
    [f"Incorrect API key provided: {KEY}", f"Bad key {KEY[:12]}****{KEY[-4:]}"],
    ids=["whole key", "masked key"],
)
async def test_a_provider_quoting_the_key_does_not_log_it(settings, provider, logs, message):
    provider.respond = lambda request: httpx.Response(401, json={"error": message})
    await _narrative()
    [line] = _fallback_lines(logs)
    assert "status=401" in line and "[key]" in line


@pytest.mark.parametrize("as_json", [True, False], ids=["raw body", "message field"])
async def test_a_provider_quoting_the_prompt_does_not_log_it(settings, provider, logs, as_json):
    def echo(request: httpx.Request) -> httpx.Response:
        sent = json.loads(request.content)
        if as_json:
            return httpx.Response(422, json={"rejected": sent})
        return httpx.Response(
            422, json={"error": {"message": sent["messages"][0]["content"]}}
        )

    provider.respond = echo
    await _narrative()
    [line] = _fallback_lines(logs)
    assert "withheld" in line
    assert "Cafe One" not in line and "Old Town" not in line


def _raise(exc: Exception):
    def _respond(request):
        raise exc

    return _respond


async def test_a_timeout_falls_back(settings, provider, logs):
    provider.respond = _raise(httpx.ReadTimeout("slow"))
    assert await _narrative() == _expected_fallback()
    [line] = _fallback_lines(logs)
    assert "reason=timeout status=none" in line


async def test_the_limit_covers_the_whole_exchange(settings, provider, logs, monkeypatch):
    async def never(request):
        await asyncio.sleep(30)

    provider.respond = never
    monkeypatch.setattr(blurbs, "NARRATIVE_TIMEOUT_SECONDS", 0.05)
    assert await asyncio.wait_for(_narrative(), 2) == _expected_fallback()
    assert "reason=timeout" in _fallback_lines(logs)[0]


def test_nobody_waits_long_for_an_intro():
    assert blurbs.NARRATIVE_TIMEOUT_SECONDS <= 8


async def test_a_failed_connection_names_only_the_kind_of_error(settings, provider, logs):
    provider.respond = _raise(httpx.ConnectError(f"cannot reach {URL}?key={KEY}"))
    assert await _narrative() == _expected_fallback()
    [line] = _fallback_lines(logs)
    assert "reason=request_failed" in line and "ConnectError" in line


@pytest.mark.parametrize(
    "address", ["not an address", "https://[broken", "model.test/v1"]
)
async def test_a_badly_written_address_does_not_break_a_quest(settings, logs, address):
    settings(url=address)
    assert await _narrative() == _expected_fallback()
    assert "reason=request_failed" in _fallback_lines(logs)[0]


@pytest.mark.parametrize(
    "response, reason",
    [
        (_answer(""), "empty_answer"),
        (_answer(None, "length"), "empty_answer"),
        (_answer([{"type": "text"}]), "empty_answer"),
        (_answer("<think>still working", "length"), "empty_answer"),
        (httpx.Response(200, json={"unexpected": True}), "empty_answer"),
        (httpx.Response(200, json=["a", "list"]), "empty_answer"),
        (httpx.Response(200, text="<html>hello</html>"), "not_json"),
        (_answer("Start at Cafe One and then", "length"), "cut_off"),
        (_answer("y" * (NARRATIVE_MAX + 1)), "too_long"),
        (httpx.Response(302, headers={"location": "https://x.test"}), "http_status"),
    ],
)
async def test_an_unusable_answer_falls_back_and_says_why(
    settings, provider, logs, response, reason
):
    provider.respond = lambda request: response
    assert await _narrative() == _expected_fallback()
    [line] = _fallback_lines(logs)
    assert f"reason={reason}" in line


async def test_a_long_answer_is_never_logged(settings, provider, logs):
    provider.respond = lambda request: _answer("zq" * NARRATIVE_MAX)
    await _narrative()
    assert "zqzq" not in logs.text


async def test_a_models_working_is_not_shown(settings, provider):
    provider.respond = lambda request: _answer("<think>Hmm.\n</think>\nA fine evening.")
    assert await _narrative() == "A fine evening."


# ── What is sent as the place ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "position",
    [
        "17.440,78.348",
        " 17.4401 , -78.3489 ",
        "+17.44, +78.35",
        "17, 78",
        "17.44 78.35",
        "17.44 N, 78.35 E",
        "17°26'24\"N 78°20'52\"E",
        "Near 17.4401, 78.3489",
        "lat 17.4401 lng 78.3489",
        "7J9WC8XX+2V",
        "C8XX+2V Old Town",
        "your area",
    ],
)
async def test_a_position_is_never_put_in_the_prompt(settings, provider, position):
    await _narrative(position)

    first_line = provider.prompt.split("Quest: ")[1].splitlines()[0]
    assert first_line == "date outing, starting in the evening, mid budget, 2 people."
    assert "stops and city" not in provider.prompt


@pytest.mark.parametrize(
    "area", ["Old Town", "Sector 17, North Side", "5th Block", "12 Main Road 560"]
)
def test_an_ordinary_area_name_is_kept(area):
    assert blurbs._prompt_area(area) == area


@pytest.mark.parametrize(
    "location, label",
    [
        ("17.440,78.348", None),
        ("17.440,78.348", "17.440, 78.348"),
        ("17.440,78.348", "+17.440,+78.348"),
        ("+17.440,+78.348", None),
    ],
)
async def test_a_device_request_sends_no_numbers(settings, provider, location, label):
    request = QuestGenerationRequest(
        location=location, location_label=label, occasion="date", cost_estimate="mid"
    )
    await _narrative(_display_location(request))
    assert "17.440" not in provider.prompt and "78.348" not in provider.prompt


# ── Blurbs ───────────────────────────────────────────────────────────────────


async def test_blurbs_use_the_same_settings(settings, provider):
    reply = json.dumps({"blurbs": [{"id": "p1", "text": "Quiet corners."}]})
    provider.respond = lambda request: _answer(f"```json\n{reply}\n```")

    assert await blurbs.generate_place_blurbs(PLACES, "cozy", "mid", 2) == {
        "p1": "Quiet corners."
    }
    [request] = provider.requests
    assert str(request.url) == URL
    assert json.loads(request.content)["model"] == NAME


async def test_oversized_blurb_input_is_cut_before_it_is_sent(settings, provider):
    huge = PlaceBlurbIn(provider_id="p" * 5000, name="n" * 5000, types=["t" * 5000] * 50)
    await blurbs.generate_place_blurbs([huge], "m" * 5000, "b" * 5000, 2)
    assert len(provider.prompt) < 2000


@pytest.mark.parametrize(
    "response, reason",
    [
        (httpx.Response(429, json={"message": "Slow down."}), "http_status"),
        (_answer(""), "empty_answer"),
        (_answer("[1, 2]"), "parse"),
        (_answer("not json at all"), "parse"),
    ],
)
async def test_blurbs_fall_back_and_say_why(settings, provider, logs, response, reason):
    provider.respond = lambda request: response
    out = await blurbs.generate_place_blurbs(PLACES, "cozy", "mid", 2)
    assert out == {"p1": blurbs._fallback_blurb(PLACES[0], "cozy", "mid")}
    assert any(f"reason={reason}" in line for line in _fallback_lines(logs))


# ── The owner's check ────────────────────────────────────────────────────────


def test_the_check_prints_the_answer(settings, provider, capsys):
    assert check_text_model.main() == 0
    out = capsys.readouterr().out
    assert "A fine evening." in out and KEY not in out
    assert len(provider.requests) == 1


async def test_the_check_asks_with_the_intros_ceiling(settings, provider):
    await _narrative()
    # The script starts an event loop of its own.
    await asyncio.to_thread(check_text_model.main)

    ceilings = [json.loads(r.content)["max_tokens"] for r in provider.requests]
    assert ceilings == [blurbs.NARRATIVE_MAX_TOKENS] * 2


def test_the_intro_leaves_room_to_think():
    assert blurbs.NARRATIVE_MAX_TOKENS == 800


@pytest.mark.parametrize(
    "response, reason",
    [(_answer("", "length"), "empty_answer"), (_answer("Half a", "length"), "cut_off")],
)
def test_the_check_says_what_thinking_may_have_done(
    settings, provider, capsys, response, reason
):
    provider.respond = lambda request: response
    assert check_text_model.main() == 1
    out = capsys.readouterr().out
    assert f"Failed: {reason}" in out
    assert "lower thinking setting" in out and "lighter model" in out


def test_the_check_prints_the_status_and_error_but_not_the_key(settings, provider, capsys):
    provider.respond = lambda request: httpx.Response(
        401, json={"error": {"message": f"No such key: {KEY}"}}
    )
    assert check_text_model.main() == 1
    out = capsys.readouterr().out
    assert "HTTP 401" in out and "No such key" in out and KEY not in out


def test_the_check_names_what_is_missing(settings, provider, capsys):
    settings(name="", key="")
    assert check_text_model.main() == 2
    out = capsys.readouterr().out
    assert "TEXT_MODEL_NAME, TEXT_MODEL_API_KEY" in out
    assert "TEXT_MODEL_URL" not in out
    assert provider.requests == []


def test_the_settings_do_not_print_the_key(settings):
    assert KEY not in repr(get_settings())
