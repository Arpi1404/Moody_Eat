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

    # Keep every Place Details response, and reuse it next time. Each place
    # not in the file costs one call.
    python -m scripts.verify_curated --saved places.json

    # Check against that file alone: no API key, no calls, nothing billed.
    python -m scripts.verify_curated --saved places.json --offline

What it checks for each stop
----------------------------
    * The provider_id resolves on Place Details (status OK, not NOT_FOUND).
    * business_status is OPERATIONAL (not CLOSED_PERMANENTLY/TEMPORARILY).
    * Rating >= 4.0 unless explicitly allowlisted via `--allow-low-rating`.
    * Lat/lng matches within ~500m of the curated value (catches typos).
    * On every weekday, the place is open for the whole scheduled visit unless
      the quest declares that day in `closed_days` for that stop, and every
      declared day is still true. A place with no hours on Google is reported,
      not failed. The logic is in `curated/hours.py`. Regular hours only:
      holidays and one-off closures are not checked.

Cost
----
One Place Details call per stop not already in the `--saved` file. `rating` and
`regularOpeningHours` are both Place Details Enterprise fields, so asking for
hours does not change what a call costs
(developers.google.com/maps/documentation/places/web-service/place-details).

Exit codes
----------
    0  All checks pass.
    1  Stale entries found (closed, missing, low rating, unresolved, or hours
       that do not match the schedule and its declared closed days).
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

from curated.hours import check_closed_days  # noqa: E402
from curated_quests import CURATED_QUESTS  # noqa: E402
from models import Quest, Stop  # noqa: E402

# Places API (New). The legacy Details / Find Place endpoints are not enabled
# for this project's key.
_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"
_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

_PLACE_FIELDS = (
    "id",
    "displayName.text",
    "formattedAddress",
    "businessStatus",
    "rating",
    "userRatingCount",
    "location",
    "types",
)
# Place Details only. Text Search (`--resolve`, lookup_place) asks for what it
# always did.
_DETAILS_FIELDS = (*_PLACE_FIELDS, "regularOpeningHours")

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
    # Worth reading, but not a failure.
    notes: list[str] = field(default_factory=list)
    resolved_place_id: str | None = None
    # `regularOpeningHours` as Google sent it. `has_details` tells a place
    # with no hours from one whose details never arrived.
    hours: dict[str, Any] | None = None
    has_details: bool = False

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


def _normalize(place: dict[str, Any]) -> dict[str, Any]:
    """A Places API (New) place in the flat shape the checks below read."""
    loc = place.get("location") or {}
    return {
        "place_id": place.get("id"),
        "name": (place.get("displayName") or {}).get("text"),
        "formatted_address": place.get("formattedAddress"),
        "business_status": place.get("businessStatus"),
        "rating": place.get("rating"),
        "user_ratings_total": place.get("userRatingCount"),
        "types": place.get("types") or [],
        "weekday_hours": (place.get("regularOpeningHours") or {}).get("weekdayDescriptions") or [],
        "opening_hours": place.get("regularOpeningHours"),
        "geometry": {"location": {"lat": loc.get("latitude"), "lng": loc.get("longitude")}},
    }


class PlaceDetails:
    """Place Details, answered from a saved file where it can be.

    The file maps a place id to the response exactly as Google sent it, so a
    check can be repeated, or run on another day's data, without paying again.
    """

    def __init__(self, api_key: str, saved_path: Path | None, *, offline: bool) -> None:
        self.api_key = api_key
        self.saved_path = saved_path
        self.offline = offline
        self.calls = 0
        self.saved: dict[str, Any] = {}
        if saved_path and saved_path.is_file():
            self.saved = json.loads(saved_path.read_text(encoding="utf-8"))

    async def get(self, client: httpx.AsyncClient, place_id: str) -> dict[str, Any]:
        """`{"status": "OK", "result": {...}}`, or a non-OK status without a result."""
        raw = self.saved.get(place_id)
        # A saved failure is asked for again rather than believed.
        if raw is None or "_error" in raw:
            if self.offline:
                return {"status": "NOT_SAVED"}
            self.calls += 1
            r = await client.get(
                _DETAILS_URL.format(place_id=place_id),
                headers={
                    "X-Goog-Api-Key": self.api_key,
                    "X-Goog-FieldMask": ",".join(_DETAILS_FIELDS),
                },
            )
            if r.status_code in (400, 404):
                # An ID Google no longer knows comes back as either, depending on its shape.
                return {"status": "NOT_FOUND"}
            r.raise_for_status()
            raw = r.json()
            if self.saved_path:
                self.saved[place_id] = raw
                self.saved_path.write_text(
                    json.dumps(self.saved, ensure_ascii=False), encoding="utf-8"
                )
        return {"status": "OK", "result": _normalize(raw)}


async def _find_place(
    client: httpx.AsyncClient,
    query: str,
    api_key: str,
    *,
    extra_fields: tuple[str, ...] = (),
) -> dict[str, Any]:
    """`{"status": "OK", "candidates": [...]}`, best match first."""
    r = await client.post(
        _TEXT_SEARCH_URL,
        headers={
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": ",".join(
                f"places.{f}" for f in (*_PLACE_FIELDS, *extra_fields)
            ),
        },
        json={"textQuery": query, "maxResultCount": 3, "languageCode": "en"},
    )
    r.raise_for_status()
    candidates = [_normalize(p) for p in r.json().get("places") or []]
    return {"status": "OK" if candidates else "ZERO_RESULTS", "candidates": candidates}


async def _verify_stop(
    client: httpx.AsyncClient,
    quest: Quest,
    stop_index: int,
    stop: Stop,
    details: PlaceDetails,
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
            data = await _find_place(client, query, details.api_key)
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
            data = await details.get(client, stop.place.provider_id)
        except httpx.HTTPError as exc:
            rep.issues.append(f"details HTTP error: {exc}")
            return rep
        status = data.get("status", "")
        if status == "NOT_SAVED":
            rep.issues.append("not in the --saved file, and --offline forbids asking Google")
            return rep
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

    if placeholder:
        rep.notes.append("hours not checked: paste the resolved ID in and run again")
    else:
        rep.hours = details_result.get("opening_hours")
        rep.has_details = True

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
    details: PlaceDetails,
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
                        details,
                        resolve=resolve,
                        allow_low_rating=allow_low_rating,
                    )
                )
            )
    reports = await asyncio.gather(*tasks)
    _check_hours(quests, reports)
    return reports


def _check_hours(quests: list[Quest], reports: list[StopReport]) -> None:
    """Add each quest's opening-hours problems to its stops' reports."""
    by_stop = {(r.quest_id, r.stop_index): r for r in reports}
    for quest in quests:
        mine = [by_stop[(str(quest.id), i)] for i in range(len(quest.stops))]
        problems, notes = check_closed_days(quest, [r.hours for r in mine])
        for index, message in problems:
            if mine[index].has_details:
                mine[index].issues.append(message)
        for index, message in notes:
            # A stop whose details never arrived is already reported.
            if mine[index].has_details:
                mine[index].notes.append(message)


def _print_report(city: str, reports: list[StopReport]) -> None:
    ok_count = sum(1 for r in reports if r.ok)
    fail_count = len(reports) - ok_count
    print(f"\n=== {city} -- {ok_count}/{len(reports)} stops OK, {fail_count} flagged ===")
    for rep in reports:
        if rep.ok and not rep.notes:
            continue
        print(f"  [{rep.quest_title}] stop {rep.stop_index + 1}: {rep.stop_name}")
        print(f"      provider_id={rep.provider_id}")
        for issue in rep.issues:
            print(f"      - {issue}")
        for note in rep.notes:
            print(f"      (note) {note}")
        if rep.resolved_place_id:
            print(f"      -> resolved place_id: {rep.resolved_place_id}")


async def _async_main(args: argparse.Namespace) -> int:
    api_key = (os.environ.get("GOOGLE_PLACES_API_KEY") or "").strip()
    if args.offline and (not args.saved or args.resolve):
        print("ERROR: --offline needs --saved, and cannot --resolve.", file=sys.stderr)
        return 2
    if not api_key and not args.offline:
        print("ERROR: GOOGLE_PLACES_API_KEY environment variable is not set.", file=sys.stderr)
        return 2
    details = PlaceDetails(
        api_key, Path(args.saved) if args.saved else None, offline=args.offline
    )
    text_searches = 0

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
                details,
                resolve=args.resolve,
                allow_low_rating=allow_low,
            )
            all_reports[city] = reports
            if args.resolve:
                text_searches += sum(
                    1 for q in quests for s in q.stops if _is_placeholder(s.place.provider_id)
                )
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

    print(f"\nGoogle calls this run: {details.calls} Place Details, {text_searches} Text Search.")

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
        help="For provider_ids prefixed 'pending:' or 'curated-', use text search to "
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
    parser.add_argument(
        "--saved",
        help="JSON file of Place Details responses: read first, and added to.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Never call Google; check only against the --saved file.",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(_async_main(args)))


if __name__ == "__main__":
    main()
