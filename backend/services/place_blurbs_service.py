"""Generate short one-line blurbs for place cards (OpenCode Zen / DeepSeek or heuristic fallback)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from typing import Any

import httpx

from models import PlaceBlurbIn


OPENCODE_URL = "https://opencode.ai/zen/v1/chat/completions"
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
    return f"{vibe} {tail} — {place.name.split()[0]} matches your {budget} plan."


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
    print(f"API key length: {len(api_key)}", file=sys.stderr, flush=True)
    print(f"API key start: {api_key[:10]}", file=sys.stderr, flush=True)
    print(f"API key end: {api_key[-10:]}", file=sys.stderr, flush=True)
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
    except (httpx.HTTPError, ValueError, KeyError):
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
                out[p.provider_id] = _fallback_blurb(p, mood, budget)
        return out
    except (json.JSONDecodeError, TypeError, KeyError):
        return {p.provider_id: _fallback_blurb(p, mood, budget) for p in places}


def _fallback_narrative(
    location: str,
    occasion: str,
    cost_estimate: str,
    stop_names: list[str],
) -> str:
    if not stop_names:
        return f"A {cost_estimate} {occasion} outing in {location}."
    if len(stop_names) == 1:
        return f"A {cost_estimate} {occasion} outing in {location}, anchored around {stop_names[0]}."
    mid = ", ".join(stop_names[:-1])
    return (
        f"A {cost_estimate} {occasion} outing in {location}: starting at {mid}, "
        f"then finishing the night at {stop_names[-1]}."
    )


async def generate_quest_narrative(
    location: str,
    occasion: str,
    cost_estimate: str,
    people: int,
    stop_summaries: list[dict[str, str]],
) -> str:
    """Return a 2-3 sentence scene-setting narrative for the whole quest.

    stop_summaries: list of {"name": ..., "category": ..., "why": ...}
    Falls back to a heuristic string when the OpenCode API is unavailable.
    """
    stop_names = [s["name"] for s in stop_summaries]
    api_key = os.environ.get("OPENCODE_API_KEY", "").strip()
    if not api_key:
        return _fallback_narrative(location, occasion, cost_estimate, stop_names)

    stops_text = "\n".join(
        f"  {i + 1}. {s['name']} ({s['category']}) — {s['why']}"
        for i, s in enumerate(stop_summaries)
    )
    prompt = f"""You write the opening narrative for a curated city quest in a travel app.

Quest: {occasion} outing, {cost_estimate} budget, {people} {'person' if people == 1 else 'people'}, in {location}.
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

    return _fallback_narrative(location, occasion, cost_estimate, stop_names)
