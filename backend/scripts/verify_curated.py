"""Verify curated quest place data against the Google Places API.

Usage
-----
    # Verify only -- fails the process if any stop is stale.
    python -m scripts.verify_curated

    # Verify and resolve `pending:` placeholder IDs into real Place IDs by
    # text search (does not write back automatically -- outputs a JSON map).
    python -m scripts.verify_curated --resolve --output resolved_ids.json

    # Limit to a single city.
    python -m scripts.verify_curated --city hyderabad

What it checks for each stop
----------------------------
    * The provider_id resolves on Place Details (status OK, not NOT_FOUND).
    * business_status is OPERATIONAL (not CLOSED_PERMANENTLY/TEMPORARILY).
    * Rating >= 4.0 unless explicitly allowlisted via `--allow-low-rating`.
    * Lat/lng matches within ~500m of the curated value (catches typos).

Exit codes
----------
    0  All checks pass.
    1  Stale entries found (closed, missing, low rating, or unresolved).
    2  Configuration / runtime error (no API key, network blocked, etc).

Notes
-----
This script loads `backend/.env` when `GOOGLE_PLACES_API_KEY` is not already in
the process environment (same key as FastAPI ``config.Settings``).

For CI, export ``GOOGLE_PLACES_API_KEY`` and run ``python -m scripts.verify_curated``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

# Make `from curated_quests import ...` work whether the script is invoked as
# `python -m scripts.verify_curated` or `python backend/scripts/verify_curated.py`.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


def _hydrate_env_from_dotenv(dotenv_path: Path) -> None:
    """Set missing env vars from a simple KEY=VALUE .env file (no python-dotenv)."""
    if not dotenv_path.is_file():
        return
    text = dotenv_path.read_text(encoding="utf-8")
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        val = value.strip()
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        if key and key not in os.environ:
            os.environ[key] = val


_hydrate_env_from_dotenv(_BACKEND_DIR / ".env")

from curated_quests import CURATED_QUESTS  # noqa: E402
from models import Quest, Stop  # noqa: E402

_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"
_FIND_PLACE_URL = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"

_DETAILS_FIELDS = "place_id,name,business_status,rating,geometry/location"
_FIND_FIELDS = "place_id,name,business_status,rating,geometry/location"

_PLACEHOLDER_PREFIX = "pending:"
_LEGACY_PLACEHOLDER_PREFIX = "curated-"

_DISTANCE_TOLERANCE_M = 500
_MIN_RATING = 4.0


@dataclass
class StopReport:
    quest_id: str
    quest_title: str
    stop_index: int
    stop_name: str
    provider_id: str
    issues: list[str] = field(default_factory=list)
    resolved_place_id: str | None = None

    @property
    def ok(self) -> bool:
        return not self.issues


def _haversine_m(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> float:
    R = 6371000.0
    p1 = math.radians(a_lat)
    p2 = math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lng - a_lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def _is_placeholder(provider_id: str) -> bool:
    return provider_id.startswith(_PLACEHOLDER_PREFIX) or provider_id.startswith(
        _LEGACY_PLACEHOLDER_PREFIX
    )


async def _details(client: httpx.AsyncClient, place_id: str, api_key: str) -> dict[str, Any]:
    r = await client.get(
        _DETAILS_URL,
        params={"place_id": place_id, "fields": _DETAILS_FIELDS, "key": api_key},
    )
    r.raise_for_status()
    return r.json()


async def _find_place(
    client: httpx.AsyncClient, query: str, api_key: str
) -> dict[str, Any]:
    r = await client.get(
        _FIND_PLACE_URL,
        params={
            "input": query,
            "inputtype": "textquery",
            "fields": _FIND_FIELDS,
            "key": api_key,
        },
    )
    r.raise_for_status()
    return r.json()


async def _verify_stop(
    client: httpx.AsyncClient,
    quest: Quest,
    stop_index: int,
    stop: Stop,
    api_key: str,
    *,
    resolve: bool,
    allow_low_rating: set[str],
) -> StopReport:
    rep = StopReport(
        quest_id=str(quest.id),
        quest_title=quest.title,
        stop_index=stop_index,
        stop_name=stop.place.name,
        provider_id=stop.place.provider_id,
    )

    placeholder = _is_placeholder(stop.place.provider_id)

    if placeholder and not resolve:
        rep.issues.append(
            f"placeholder provider_id '{stop.place.provider_id}' -- run with --resolve to discover the real Place ID"
        )
        return rep

    details_result: dict[str, Any] | None = None

    if placeholder and resolve:
        query = f"{stop.place.name}, {stop.place.address}"
        try:
            data = await _find_place(client, query, api_key)
        except httpx.HTTPError as exc:
            rep.issues.append(f"find_place HTTP error: {exc}")
            return rep
        status = data.get("status", "")
        if status != "OK" or not data.get("candidates"):
            rep.issues.append(
                f"find_place could not resolve '{query}' (status={status})"
            )
            return rep
        candidate = data["candidates"][0]
        rep.resolved_place_id = candidate.get("place_id")
        details_result = candidate
    else:
        try:
            data = await _details(client, stop.place.provider_id, api_key)
        except httpx.HTTPError as exc:
            rep.issues.append(f"details HTTP error: {exc}")
            return rep
        status = data.get("status", "")
        if status == "NOT_FOUND":
            rep.issues.append(f"place_id '{stop.place.provider_id}' returned NOT_FOUND")
            return rep
        if status != "OK":
            rep.issues.append(f"place details returned status={status}")
            return rep
        details_result = data.get("result")
        if not details_result:
            rep.issues.append("place details returned an empty result")
            return rep

    business_status = details_result.get("business_status")
    if business_status and business_status != "OPERATIONAL":
        rep.issues.append(f"business_status={business_status}")

    rating = details_result.get("rating")
    if isinstance(rating, (int, float)) and rating < _MIN_RATING:
        if stop.place.provider_id in allow_low_rating:
            pass
        else:
            rep.issues.append(
                f"rating={rating:.1f} < {_MIN_RATING} (add to --allow-low-rating if intentional)"
            )

    loc = (details_result.get("geometry") or {}).get("location") or {}
    lat = loc.get("lat")
    lng = loc.get("lng")
    if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
        delta = _haversine_m(stop.place.lat, stop.place.lng, float(lat), float(lng))
        if delta > _DISTANCE_TOLERANCE_M:
            rep.issues.append(
                f"location off by {int(delta)}m (curated {stop.place.lat:.4f},{stop.place.lng:.4f} "
                f"vs api {float(lat):.4f},{float(lng):.4f})"
            )

    return rep


async def _verify_city(
    client: httpx.AsyncClient,
    city: str,
    quests: list[Quest],
    api_key: str,
    *,
    resolve: bool,
    allow_low_rating: set[str],
) -> list[StopReport]:
    tasks: list[asyncio.Task[StopReport]] = []
    for quest in quests:
        for idx, stop in enumerate(quest.stops):
            tasks.append(
                asyncio.create_task(
                    _verify_stop(
                        client,
                        quest,
                        idx,
                        stop,
                        api_key,
                        resolve=resolve,
                        allow_low_rating=allow_low_rating,
                    )
                )
            )
    return await asyncio.gather(*tasks)


def _print_report(city: str, reports: list[StopReport]) -> None:
    ok_count = sum(1 for r in reports if r.ok)
    fail_count = len(reports) - ok_count
    print(f"\n=== {city} -- {ok_count}/{len(reports)} stops OK, {fail_count} flagged ===")
    for rep in reports:
        if rep.ok:
            continue
        print(f"  [{rep.quest_title}] stop {rep.stop_index + 1}: {rep.stop_name}")
        print(f"      provider_id={rep.provider_id}")
        for issue in rep.issues:
            print(f"      - {issue}")
        if rep.resolved_place_id:
            print(f"      -> resolved place_id: {rep.resolved_place_id}")


async def _async_main(args: argparse.Namespace) -> int:
    api_key = (os.environ.get("GOOGLE_PLACES_API_KEY") or "").strip()
    if not api_key:
        print("ERROR: GOOGLE_PLACES_API_KEY environment variable is not set.", file=sys.stderr)
        return 2

    cities = [args.city.lower()] if args.city else sorted(set(CURATED_QUESTS.keys()))
    allow_low = set(args.allow_low_rating or [])

    all_reports: dict[str, list[StopReport]] = {}
    resolved_map: dict[str, str] = {}

    timeout = httpx.Timeout(10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        for city in cities:
            quests = CURATED_QUESTS.get(city)
            if not quests:
                print(f"WARNING: city '{city}' has no curated quests, skipping.")
                continue
            reports = await _verify_city(
                client,
                city,
                quests,
                api_key,
                resolve=args.resolve,
                allow_low_rating=allow_low,
            )
            all_reports[city] = reports
            for rep in reports:
                if rep.resolved_place_id and rep.provider_id.startswith(_PLACEHOLDER_PREFIX):
                    resolved_map[rep.provider_id] = rep.resolved_place_id

    failures = 0
    for city, reports in all_reports.items():
        _print_report(city, reports)
        failures += sum(1 for r in reports if not r.ok)

    if args.resolve and args.output and resolved_map:
        Path(args.output).write_text(json.dumps(resolved_map, indent=2))
        print(f"\nWrote {len(resolved_map)} resolved IDs -> {args.output}")

    if failures:
        print(f"\n{failures} stop(s) need attention. Failing.")
        return 1

    print("\nAll curated stops verified.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--city",
        help="Verify only one city key (e.g. 'hyderabad'). Default: all cities.",
    )
    parser.add_argument(
        "--resolve",
        action="store_true",
        help="For provider_ids prefixed 'pending:' or 'curated-', use Find Place text search to "
        "discover real Place IDs by name+address.",
    )
    parser.add_argument(
        "--output",
        help="When --resolve is set, write the discovered placeholder->real-id map to this JSON path.",
    )
    parser.add_argument(
        "--allow-low-rating",
        nargs="*",
        help="provider_ids whose rating below 4.0 is intentional and acceptable.",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(_async_main(args)))


if __name__ == "__main__":
    main()
