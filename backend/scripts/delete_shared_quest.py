"""Take down a shared quest, so its /q/ link stops working.

Usage
-----
    cd backend
    python -m scripts.delete_shared_quest <short_id or /q/ link> [--yes]

It shows what the quest says and asks before deleting. It works on whichever
store the environment points at, exactly as the API does: the local SQLite
file by default. For the live site:

    gcloud auth application-default login
    QUEST_STORE_BACKEND=firestore FIRESTORE_PROJECT=<project> \\
        python -m scripts.delete_shared_quest <short_id>

Deleting cannot reach copies already opened or saved in a browser, downloaded
story cards, or link previews that other apps have cached. It also does not
stop anyone sharing the same words again under a new link.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from models import tidy_text  # noqa: E402
from quest_store import delete_quest, describe_store, fetch_quest  # noqa: E402

_SHORT_ID_RE = re.compile(r"[a-z0-9]{4,16}")


def parse_short_id(value: str) -> str | None:
    """The id from "abcd2345" or from a link ending /q/abcd2345."""
    text = value.strip().split("#")[0].split("?")[0].rstrip("/")
    if "/q/" in text:
        text = text.rsplit("/q/", 1)[1]
    return text if _SHORT_ID_RE.fullmatch(text) else None


def _shown(value: object) -> str:
    # Anyone can write a shared quest: strip control characters so it cannot
    # send escape codes to this terminal.
    return tidy_text(str(value or ""))


def describe_quest(quest_json: str) -> list[str]:
    quest = json.loads(quest_json)
    lines = [
        f"  Title:   {_shown(quest.get('title'))}",
        f"  Made by: {_shown(quest.get('created_by')) or '-'}",
        f"  Intro:   {_shown(quest.get('narrative'))}",
    ]
    for number, stop in enumerate(quest.get("stops") or [], start=1):
        place = stop.get("place") or {}
        lines.append(
            f"  Stop {number}:  {_shown(place.get('name'))} | "
            f"{_shown(stop.get('why_this_place'))}"
        )
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Delete a shared quest.")
    parser.add_argument("quest", help="short id, or the quest's /q/ link")
    parser.add_argument("--yes", action="store_true", help="do not ask first")
    args = parser.parse_args(argv)

    short_id = parse_short_id(args.quest)
    if short_id is None:
        print("That is not a short id or a /q/ link.", file=sys.stderr)
        return 2

    print(f"Store: {describe_store()}")
    stored = fetch_quest(short_id, count_view=False)
    if stored is None:
        print(f"No shared quest '{short_id}' in this store.", file=sys.stderr)
        return 1

    print(f"Quest {short_id}, stored {stored.created_at}, opened {stored.views} times")
    print("\n".join(describe_quest(stored.quest_json)))
    if not args.yes:
        answer = input("Delete this quest? This cannot be undone. [y/N] ")
        if answer.strip().lower() not in ("y", "yes"):
            print("Kept.")
            return 1

    if not delete_quest(short_id):
        print("It was already gone.", file=sys.stderr)
        return 1
    print(f"Deleted. /q/{short_id} no longer works.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
