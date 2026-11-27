"""What people swapped out, and what they chose instead.

Reads the swap log (see swap_log.py) and prints the places most often
replaced, the places most often chosen, and the most common replacements,
overall or for one occasion.

    python -m scripts.swap_report                      # local SQLite store
    python -m scripts.swap_report --occasion date
    QUEST_STORE_BACKEND=firestore FIRESTORE_PROJECT=<project-id> \\
        python -m scripts.swap_report                  # production

Production needs `gcloud auth application-default login` first.

Only place ids are stored, so each line links to the place on Google Maps
instead of naming it. Counts are raw: one person can swap many times, and
anyone can post to the endpoint, so read small numbers as anecdotes.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from swap_log import load_swaps  # noqa: E402


def maps_link(place_id: str) -> str:
    return f"https://www.google.com/maps/place/?q=place_id:{place_id}"


def summarize(swaps: list[dict[str, Any]], occasion: str | None = None) -> dict[str, Any]:
    """Counts over the swap log, optionally for one occasion."""
    if occasion:
        swaps = [swap for swap in swaps if swap.get("occasion") == occasion]
    return {
        "total": len(swaps),
        "by_occasion": Counter(swap.get("occasion") for swap in swaps),
        "by_origin": Counter(swap.get("quest_origin") or "unknown" for swap in swaps),
        "replaced": Counter(swap["from_place_id"] for swap in swaps),
        "chosen": Counter(swap["to_place_id"] for swap in swaps),
        "pairs": Counter((swap["from_place_id"], swap["to_place_id"]) for swap in swaps),
    }


def _print_places(title: str, counts: Counter, top: int) -> None:
    print(f"\n{title}")
    for place_id, count in counts.most_common(top):
        print(f"  {count:>4}  {maps_link(place_id)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--occasion", choices=["date", "friends", "solo", "family"])
    parser.add_argument("--top", type=int, default=10, help="rows per list (default 10)")
    args = parser.parse_args()

    summary = summarize(load_swaps(), args.occasion)
    scope = f" for {args.occasion} quests" if args.occasion else ""
    print(f"{summary['total']} swaps recorded{scope}")
    if not summary["total"]:
        return
    print("by occasion:", dict(summary["by_occasion"]))
    print("by quest origin:", dict(summary["by_origin"]))
    _print_places("Most often replaced", summary["replaced"], args.top)
    _print_places("Most often chosen", summary["chosen"], args.top)
    print("\nMost common replacements")
    for (from_id, to_id), count in summary["pairs"].most_common(args.top):
        print(f"  {count:>4}  {maps_link(from_id)}\n     -> {maps_link(to_id)}")


if __name__ == "__main__":
    main()
