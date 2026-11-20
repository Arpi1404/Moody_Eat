"""Look venues up on Google Places and print them as `place(...)` calls.

Usage
-----
    python -m scripts.lookup_place "Toit, Indiranagar, Bangalore" "MTR, Lalbagh Road, Bangalore"

Each query prints the best match as a block ready to paste into
`curated/<city>.py`, with the real Place ID, coordinates, rating and review
count, plus opening hours and a warning when the venue is closed or rated
under 4.0. Check the
printed name and address — a vague query can match the wrong branch.

Uses the same `GOOGLE_PLACES_API_KEY` as the API (read from `backend/.env`).
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import httpx

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from scripts.verify_curated import _MIN_RATING, _find_place  # noqa: E402

# Google's generic tags say nothing about a venue.
_NOISE_TYPES = {"point_of_interest", "establishment", "food", "store"}


async def _lookup(client: httpx.AsyncClient, query: str, api_key: str) -> str:
    data = await _find_place(
        client, query, api_key, extra_fields=("regularOpeningHours.weekdayDescriptions",)
    )
    candidates = data["candidates"]
    if not candidates:
        return f"# {query}\n#   NOT FOUND\n"

    c = candidates[0]
    loc = (c.get("geometry") or {}).get("location") or {}
    rating = c.get("rating")
    status = c.get("business_status") or "UNKNOWN"
    types = [t for t in c.get("types") or [] if t not in _NOISE_TYPES][:3]

    warnings = []
    if status != "OPERATIONAL":
        warnings.append(f"business_status={status}")
    if not isinstance(rating, (int, float)):
        warnings.append("no rating")
    elif rating < _MIN_RATING:
        warnings.append(f"rating {rating} is under {_MIN_RATING}")
    if len(candidates) > 1:
        warnings.append(f"{len(candidates)} matches, showing the first")

    lines = [f"# {query}"]
    lines += [f"#   WARNING: {w}" for w in warnings]
    lines += [
        "place(",
        f'    "{c.get("place_id")}",',
        f'    "{c.get("name")}",',
        f'    "{c.get("formatted_address")}",',
        f"    {loc.get('lat'):.4f},",
        f"    {loc.get('lng'):.4f},",
        f"    {rating if rating is not None else 0.0},",
        f"    {types!r},".replace("'", '"'),
        f"    {c.get('user_ratings_total') or 0},",
        "),",
    ]
    hours = c.get("weekday_hours") or []
    lines += [f"#   hours: {h}" for h in hours] or ["#   hours: not listed"]
    return "\n".join(lines) + "\n"


async def _main(queries: list[str]) -> int:
    api_key = (os.environ.get("GOOGLE_PLACES_API_KEY") or "").strip()
    if not api_key:
        print("ERROR: GOOGLE_PLACES_API_KEY is not set.", file=sys.stderr)
        return 2
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        blocks = await asyncio.gather(*(_lookup(client, q, api_key) for q in queries))
    print("\n".join(blocks))
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(asyncio.run(_main(sys.argv[1:])))
