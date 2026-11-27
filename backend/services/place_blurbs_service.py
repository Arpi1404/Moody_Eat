"""Generate short one-line blurbs for place cards (OpenCode Zen / DeepSeek or heuristic fallback)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from typing import Any

import httpx

from models import PlaceBlurbIn

logger = logging.getLogger(__name__)


OPENCODE_URL = "https://opencode.ai/zen/go/v1/chat/completions"
MODEL = "deepseek-v4-flash"


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


def _opencode_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "content-type": "application/json",
    }


def _extract_text(data: dict[str, Any]) -> str:
    try:
        return (data["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError):
        return ""


async def generate_place_blurbs(
    places: list[PlaceBlurbIn],
    mood: str,
    budget: str,
    people: int,
) -> dict[str, str]:
    if not places:
        return {}

    api_key = os.environ.get("OPENCODE_API_KEY", "").strip()
    if not api_key:
        return {p.provider_id: _fallback_blurb(p, mood, budget) for p in places}

    payload_places: list[dict[str, Any]] = [
        {
            "id": p.provider_id,
            "name": p.name,
            "types": p.types[:8] if p.types else [],
        }
        for p in places
    ]

    prompt = f"""You write ultra-short venue taglines for a travel app (not marketing fluff).

Trip: mood={mood!r}, budget tier={budget!r}, party size={people}.

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

    body = {
        "model": MODEL,
        "max_tokens": 2048,
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            res = await client.post(OPENCODE_URL, headers=_opencode_headers(api_key), json=body)
            res.raise_for_status()
            data = res.json()
    except (httpx.HTTPError, ValueError, KeyError) as e:
        logger.warning("blurbs_fallback reason=http err_type=%s", type(e).__name__)
        return {p.provider_id: _fallback_blurb(p, mood, budget) for p in places}

    try:
        text = _extract_text(data)
        text = re.sub(r"^```(?:json)?\s*", "", text)
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
    except (json.JSONDecodeError, TypeError, KeyError) as e:
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
    Falls back to a heuristic string when the OpenCode API is unavailable.
    """
    stop_names = [s["name"] for s in stop_summaries]
    api_key = os.environ.get("OPENCODE_API_KEY", "").strip()
    if not api_key:
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
    prompt = f"""You write the opening narrative for a curated city quest in a travel app.

Quest: {occasion} outing{when}, {cost_estimate} budget, {people} {'person' if people == 1 else 'people'}, in {location}.
Stops:
{stops_text}

Write exactly 2-3 sentences that set the scene for this outing. Be vivid and specific to the stops and city. No marketing language, no bullet points, no headers — plain prose only."""

    body = {
        "model": MODEL,
        "max_tokens": 256,
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(OPENCODE_URL, headers=_opencode_headers(api_key), json=body)
            res.raise_for_status()
            data = res.json()
        text = _extract_text(data)
        if text:
            return text
    except (httpx.HTTPError, ValueError, KeyError):
        pass

    return _fallback_narrative(location, occasion, cost_estimate, stop_names, day_part)
