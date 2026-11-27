"""Record of stop swaps: which suggested place someone replaced, and with what.

Why this exists: the engine picks places by rating, popularity, price and
distance, and knows nothing about taste. A swap is the one moment a person
tells us "not this place, that one, for this kind of outing". Collected over
time, swaps are our own signal for which places suit which occasion.

What is stored: Google place ids (the one piece of Places content Google
allows keeping indefinitely) and the context of the choice — occasion, stop
category, budget, the stop's start time, what else was on offer. Nothing about
the person: no quest id, no IP address, no coordinates, no free text.

What it is not, yet: an input to ranking. Anyone can post to the endpoint, so
before these counts influence what people are shown they need a guard against
one source voting many times (see HANDOFF.md).

Storage follows the shared-quest store: the same SQLite file locally, the
same Firestore database on Cloud Run (QUEST_STORE_BACKEND).

All functions are synchronous; call them from async routes via
fastapi.concurrency.run_in_threadpool.
"""

from __future__ import annotations

import json
from contextlib import closing
from typing import Any

import quest_store
from models import SwapEvent

SWAPS_COLLECTION = "swap_events"
SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS swap_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    v INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    from_place_id TEXT NOT NULL,
    to_place_id TEXT NOT NULL,
    shown_place_ids TEXT NOT NULL,
    chosen_rank INTEGER,
    occasion TEXT NOT NULL,
    category TEXT NOT NULL,
    budget TEXT NOT NULL,
    stop_index INTEGER NOT NULL,
    stop_count INTEGER NOT NULL,
    slot_start TEXT NOT NULL,
    quest_origin TEXT
)
"""

# Column order for inserts and reads; `id` is SQLite's own.
_FIELDS = (
    "v",
    "created_at",
    "from_place_id",
    "to_place_id",
    "shown_place_ids",
    "chosen_rank",
    "occasion",
    "category",
    "budget",
    "stop_index",
    "stop_count",
    "slot_start",
    "quest_origin",
)


def _record(event: SwapEvent) -> dict[str, Any]:
    """The stored form of a swap. Every key here is listed in _FIELDS; adding
    one is a decision about what we keep, so the tests pin the exact set."""
    shown = list(event.shown_place_ids)
    return {
        "v": SCHEMA_VERSION,
        "created_at": quest_store._now_iso(),
        "from_place_id": event.from_place_id,
        "to_place_id": event.to_place_id,
        "shown_place_ids": shown,
        # Position of the chosen place in the list as shown (0 = first). The
        # first option gets picked more just for being first; this lets a
        # reader of the data correct for that.
        "chosen_rank": shown.index(event.to_place_id) if event.to_place_id in shown else None,
        "occasion": event.occasion.value,
        "category": event.category.value,
        "budget": event.budget.value,
        "stop_index": event.stop_index,
        "stop_count": event.stop_count,
        "slot_start": event.slot_start.strftime("%H:%M"),
        "quest_origin": event.quest_origin,
    }


def record_swap(event: SwapEvent) -> None:
    """Persist one swap."""
    record = _record(event)
    if quest_store._backend() == "firestore":
        quest_store.firestore_client().collection(SWAPS_COLLECTION).add(record)
        return
    row = {**record, "shown_place_ids": json.dumps(record["shown_place_ids"])}
    with closing(quest_store._connect()) as conn, conn:
        conn.execute(_SCHEMA)
        conn.execute(
            f"INSERT INTO swap_events ({', '.join(_FIELDS)})"
            f" VALUES ({', '.join('?' for _ in _FIELDS)})",
            tuple(row[field] for field in _FIELDS),
        )


def load_swaps() -> list[dict[str, Any]]:
    """Every stored swap, oldest first. For reports, not for request paths:
    it reads the whole collection."""
    if quest_store._backend() == "firestore":
        docs = quest_store.firestore_client().collection(SWAPS_COLLECTION).stream()
        swaps = [doc.to_dict() for doc in docs]
        swaps.sort(key=lambda swap: swap.get("created_at") or "")
        return swaps
    with closing(quest_store._connect()) as conn, conn:
        conn.execute(_SCHEMA)
        rows = conn.execute(
            f"SELECT {', '.join(_FIELDS)} FROM swap_events ORDER BY id"
        ).fetchall()
    return [
        {**dict(row), "shown_place_ids": json.loads(row["shown_place_ids"])}
        for row in rows
    ]
