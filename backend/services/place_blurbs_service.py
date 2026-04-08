"""Generate short one-line blurbs for place cards (Claude or heuristic fallback)."""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

import httpx

from models import PlaceBlurbIn

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-3-5-haiku-20241022"


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


async def generate_place_blurbs(
    places: list[PlaceBlurbIn],
    mood: str,
    budget: str,
    people: int,
) -> dict[str, str]:
    if not places:
        return {}

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
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

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL),
        "max_tokens": 2048,
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            res = await client.post(ANTHROPIC_URL, headers=headers, json=body)
            res.raise_for_status()
            data = res.json()
    except (httpx.HTTPError, ValueError, KeyError):
        return {p.provider_id: _fallback_blurb(p, mood, budget) for p in places}

    try:
        text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                text += block.get("text", "")
        text = text.strip()
        # Strip accidental fences
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
