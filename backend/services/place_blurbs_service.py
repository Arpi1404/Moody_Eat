"""Quest intros and place-card blurbs from a text model, or fallback text.

Any provider with a chat-completions endpoint works. Three settings choose it
(see config.py): TEXT_MODEL_URL, TEXT_MODEL_NAME and TEXT_MODEL_API_KEY. With
any of them missing, nothing is sent and the fallback text is used. Whenever a
configured model's answer is not used, one log line says why. The key, the
prompt and the full response are never logged.

`python -m scripts.check_text_model` tries the settings out.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

from config import get_settings
from models import NARRATIVE_MAX, PlaceBlurbIn

logger = logging.getLogger(__name__)


# The intro is awaited while a quest is being built, so this is the most a slow
# provider can add to anyone's wait. It is a limit on the whole exchange.
NARRATIVE_TIMEOUT_SECONDS = 8.0
# Blurbs are fetched after the places are already on screen, and are longer.
BLURBS_TIMEOUT_SECONDS = 20.0

# How much of a provider's error message goes into a log line.
_ERROR_SNIPPET_MAX = 200
# A stretch of an error message this long that also appears in the prompt means
# the provider is quoting the request back.
_ECHO_WINDOW = 24
# A stretch of the key this long is hidden, for messages that quote part of it.
_KEY_PIECE = 8


def _fallback_blurb(place: PlaceBlurbIn, mood: str, budget: str) -> str:
    """Deterministic, human-ish line when API is unavailable."""
    h = int(hashlib.md5(place.provider_id.encode(), usedforsecurity=False).hexdigest()[:8], 16)
    types_hint = ""
    if place.types:
        t = next(
            (x for x in place.types if x not in ("establishment", "point_of_interest", "premise")),
            None,
        )
        if t:
            types_hint = t.replace("_", " ")
    vibe = [
        "A solid pick for",
        "Worth a stop when you're after",
        "Fits the bill for",
        "Great when you want",
    ][h % 4]
    tail = f"a {mood} outing" if not types_hint else f"a {mood} {types_hint} vibe"
    return f"{vibe} {tail} — and it fits your {budget} plan."


@dataclass(frozen=True)
class TextModel:
    url: str
    name: str
    api_key: str


def configured_text_model() -> TextModel | None:
    """The model to ask, or None unless all three settings have a value."""
    settings = get_settings()
    values = (
        settings.text_model_url.strip(),
        settings.text_model_name.strip(),
        settings.text_model_api_key.strip(),
    )
    return TextModel(*values) if all(values) else None


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "content-type": "application/json",
    }


def _extract_text(data: dict[str, Any]) -> str:
    try:
        return (data["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError, AttributeError):
        return ""


def _finish_reason(data: Any) -> str | None:
    try:
        reason = data["choices"][0]["finish_reason"]
    except (KeyError, IndexError, TypeError):
        return None
    return reason if isinstance(reason, str) else None


# Some reasoning models put their working in the answer, ahead of the reply.
_THINKING_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _without_thinking(text: str) -> str:
    text = _THINKING_RE.sub("", text).strip()
    # Unfinished working: there is no reply in it.
    return "" if "<think>" in text else text


def _error_message(res: httpx.Response) -> str:
    """The provider's own words, from the usual places or else the raw body."""
    try:
        body = res.json()
        error = body.get("error", body) if isinstance(body, dict) else None
        if isinstance(error, str):
            return error
        if isinstance(error, dict):
            for field in ("message", "detail"):
                if isinstance(error.get(field), str):
                    return error[field]
    except ValueError:
        pass
    return res.text


def _safe_snippet(message: str, api_key: str, prompt: str) -> str:
    """A short piece of an error message that is safe to log."""
    text = " ".join(message.split()).replace(api_key, "[key]")
    for start in range(len(api_key) - _KEY_PIECE + 1):
        text = text.replace(api_key[start : start + _KEY_PIECE], "[key]")
    text = text[:_ERROR_SNIPPET_MAX]
    # Compared without spacing or escapes, so a JSON-quoted echo still matches.
    def bare(value: str) -> str:
        return re.sub(r"\\[nrt]|[\s\\]", "", value)

    quoted, sent = bare(text), bare(prompt)
    if any(
        quoted[i : i + _ECHO_WINDOW] in sent
        for i in range(len(quoted) - _ECHO_WINDOW + 1)
    ):
        return "[withheld: it repeats the request]"
    return text


@dataclass(frozen=True)
class ModelReply:
    text: str = ""
    # None when `text` can be used; otherwise a short word for what went wrong.
    problem: str | None = None
    status: int | None = None
    detail: str = ""


async def ask_model(
    model: TextModel, prompt: str, max_tokens: int, timeout: float
) -> ModelReply:
    """Send one prompt. Never raises: a failure comes back as a ModelReply."""
    body = {
        "model": model.name,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            # httpx times each read separately, so a reply that trickles in
            # needs a limit on the whole exchange too.
            res = await asyncio.wait_for(
                client.post(model.url, headers=_headers(model.api_key), json=body),
                timeout,
            )
        if not res.is_success:
            return ModelReply(
                problem="http_status",
                status=res.status_code,
                detail=_safe_snippet(_error_message(res), model.api_key, prompt),
            )
        try:
            data = res.json()
        except ValueError:
            return ModelReply(problem="not_json", status=res.status_code)
    except (asyncio.TimeoutError, httpx.TimeoutException):
        return ModelReply(problem="timeout", detail=f"no answer in {timeout:g}s")
    except Exception as exc:  # noqa: BLE001 - a quest must not fail over this
        # Only the type: some of these messages quote the address or a header.
        return ModelReply(problem="request_failed", detail=type(exc).__name__)

    text = _without_thinking(_extract_text(data))
    finish = _finish_reason(data)
    if not text:
        problem = "empty_answer"
    elif finish == "length":
        # The token ceiling cut it off, most likely in mid-sentence.
        problem = "cut_off"
    else:
        return ModelReply(text=text, status=res.status_code)
    detail = f"finish_reason={_safe_snippet(finish or 'none', model.api_key, prompt)}"
    return ModelReply(problem=problem, status=res.status_code, detail=detail)


def _log_fallback(what: str, reply: ModelReply) -> None:
    logger.warning(
        "%s_fallback reason=%s status=%s detail=%r",
        what,
        reply.problem,
        reply.status if reply.status is not None else "none",
        reply.detail,
    )


# Anything that gives a position as numbers: degrees, a decimal with three or
# more places, a Plus Code, or a bare pair of numbers.
_POSITION_RES = (
    re.compile(r"°"),
    re.compile(r"\d\.\d{3,}"),
    re.compile(r"\b[23456789CFGHJMPQRVWX]{4,8}\+[23456789CFGHJMPQRVWX]{2,3}\b", re.I),
    re.compile(
        r"^\W*[-+]?\d+(?:\.\d+)?\s*[NSEW]?\s*[,;/ ]\s*[-+]?\d+(?:\.\d+)?\s*[NSEW]?\W*$",
        re.I,
    ),
)


def _prompt_area(location: str) -> str:
    """The area as it may go into a prompt, or "" to leave it out.

    The caller passes a readable label already. This is the last check that a
    device position, however it is written, never reaches the provider.
    """
    area = " ".join(location.split())
    # "your area" is what the caller passes when it only has coordinates.
    if area.lower() == "your area" or any(p.search(area) for p in _POSITION_RES):
        return ""
    return area[:120]


async def generate_place_blurbs(
    places: list[PlaceBlurbIn],
    mood: str,
    budget: str,
    people: int,
) -> dict[str, str]:
    if not places:
        return {}

    model = configured_text_model()
    if model is None:
        return {p.provider_id: _fallback_blurb(p, mood, budget) for p in places}

    # The endpoint is public and takes free text, so what goes into the prompt
    # is cut to the sizes real values have.
    payload_places: list[dict[str, Any]] = [
        {
            "id": p.provider_id[:300],
            "name": p.name[:120],
            "types": [t[:40] for t in p.types[:8]] if p.types else [],
        }
        for p in places
    ]

    prompt = f"""You write ultra-short venue taglines for a travel app (not marketing fluff).

Trip: mood={mood[:40]!r}, budget tier={budget[:40]!r}, party size={people}.

For each place below, return ONE JSON object only, no markdown:
{{"blurbs":[{{"id":"<exact id>","text":"<one line max 120 chars>"}}]}}

Rules:
- One line each; vivid, specific; mention vibe or social context when natural.
- Do not repeat the place name verbatim if avoidable.
- Match the user's mood and budget subtly.
- JSON only.

Places:
{json.dumps(payload_places, ensure_ascii=False)}
"""

    reply = await ask_model(model, prompt, 2048, BLURBS_TIMEOUT_SECONDS)
    if reply.problem:
        _log_fallback("blurbs", reply)
        return {p.provider_id: _fallback_blurb(p, mood, budget) for p in places}

    try:
        text = re.sub(r"^```(?:json)?\s*", "", reply.text)
        text = re.sub(r"\s*```\s*$", "", text)
        parsed = json.loads(text)
        out: dict[str, str] = {}
        for row in parsed.get("blurbs", []):
            pid = row.get("id")
            line = (row.get("text") or "").strip()
            if pid and line:
                out[str(pid)] = line[:200]
        for p in places:
            if p.provider_id not in out:
                logger.info("blurbs_fallback reason=missing_blurb")
                out[p.provider_id] = _fallback_blurb(p, mood, budget)
        return out
    except (json.JSONDecodeError, TypeError, KeyError, AttributeError) as e:
        logger.warning("blurbs_fallback reason=parse err_type=%s", type(e).__name__)
        return {p.provider_id: _fallback_blurb(p, mood, budget) for p in places}


# What the outing is called in a sentence, by occasion and time of day. The
# None entry is for callers that do not say when it starts.
# Mirrored by rebuildNarrative in frontend/src/pages/QuestPage.tsx, which
# rewrites the sentence after a stop is swapped: change one, change both.
_OUTING_PHRASES: dict[str, dict[str | None, str]] = {
    "date": {
        "morning": "morning date",
        "afternoon": "afternoon date",
        "evening": "evening date",
        "night": "date night",
        None: "date",
    },
    "friends": {
        "morning": "morning out with friends",
        "afternoon": "afternoon out with friends",
        "evening": "evening out with friends",
        "night": "night out with friends",
        None: "outing with friends",
    },
    "solo": {
        "morning": "solo morning",
        "afternoon": "solo afternoon",
        "evening": "solo evening",
        "night": "solo night out",
        None: "solo outing",
    },
    "family": {
        "morning": "family morning out",
        "afternoon": "family afternoon out",
        "evening": "family evening out",
        "night": "family night out",
        None: "family outing",
    },
}
# "mid" is our word for the middle budget, not one a person would use, so it
# adds nothing to the sentence.
_BUDGET_WORDS: dict[str, str] = {"cheap": "budget-friendly", "splurge": "splurge-worthy"}


def _outing_phrase(occasion: str, cost_estimate: str, day_part: str | None) -> str:
    """The outing in words: "An evening date", "A budget-friendly solo morning"."""
    by_part = _OUTING_PHRASES.get(occasion)
    if by_part is None:
        phrase = f"{occasion} outing"
    else:
        phrase = by_part.get(day_part) or by_part[None]
    budget = _BUDGET_WORDS.get(cost_estimate)
    if budget:
        phrase = f"{budget} {phrase}"
    article = "An" if phrase[:1].lower() in "aeiou" else "A"
    return f"{article} {phrase}"


def _fallback_narrative(
    location: str,
    occasion: str,
    cost_estimate: str,
    stop_names: list[str],
    day_part: str | None = None,
) -> str:
    lead = _outing_phrase(occasion, cost_estimate, day_part)
    intro = f"{lead} in {location}" if location else lead
    if not stop_names:
        return f"{intro}."
    if len(stop_names) == 1:
        return f"{intro}, built around {stop_names[0]}."
    first, last = stop_names[0], stop_names[-1]
    between = stop_names[1:-1]
    if not between:
        return f"{intro}: start at {first}, then finish at {last}."
    if len(between) == 1:
        middle = between[0]
    else:
        middle = f"{', '.join(between[:-1])} and {between[-1]}"
    return f"{intro}: start at {first}, move on to {middle}, then finish at {last}."


async def generate_quest_narrative(
    location: str,
    occasion: str,
    cost_estimate: str,
    people: int,
    stop_summaries: list[dict[str, str]],
    day_part: str | None = None,
) -> str:
    """Return a 2-3 sentence scene-setting narrative for the whole quest.

    stop_summaries: list of {"name": ..., "category": ..., "why": ...}
    day_part: "morning" | "afternoon" | "evening" | "night" when known, so the
    text does not call a morning plan a night out.
    Falls back to a heuristic string when no model is configured or its
    answer cannot be used.
    """
    stop_names = [s["name"] for s in stop_summaries]
    model = configured_text_model()
    if model is None:
        return _fallback_narrative(location, occasion, cost_estimate, stop_names, day_part)

    stops_text = "\n".join(
        f"  {i + 1}. {s['name']} ({s['category']}) — {s['why']}"
        for i, s in enumerate(stop_summaries)
    )
    if not day_part:
        when = ""
    elif day_part == "night":
        when = ", starting at night"
    else:
        when = f", starting in the {day_part}"
    area = _prompt_area(location)
    in_area = f", in {area}" if area else ""
    specific_to = "the stops and city" if area else "the stops"
    prompt = f"""You write the opening narrative for a curated city quest in a travel app.

Quest: {occasion} outing{when}, {cost_estimate} budget, {people} {'person' if people == 1 else 'people'}{in_area}.
Stops:
{stops_text}

Write exactly 2-3 sentences that set the scene for this outing. Be vivid and specific to {specific_to}. No marketing language, no bullet points, no headers — plain prose only."""

    reply = await ask_model(model, prompt, 256, NARRATIVE_TIMEOUT_SECONDS)
    if reply.problem is None and len(reply.text) > NARRATIVE_MAX:
        reply = ModelReply(
            problem="too_long",
            status=reply.status,
            detail=f"{len(reply.text)} characters, limit {NARRATIVE_MAX}",
        )
    if reply.problem:
        _log_fallback("narrative", reply)
        return _fallback_narrative(location, occasion, cost_estimate, stop_names, day_part)
    return reply.text
