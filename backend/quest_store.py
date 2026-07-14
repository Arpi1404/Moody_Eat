"""SQLite-backed store for shared quests (short links).

Shared quests otherwise live only in the creator's browser, so share links
had to carry the whole quest in an 800-char #q= fragment. Storing the quest
server-side gives moodyeat.in/q/<short_id> links, per-quest OG previews for
crawlers, and a view count — the receiving side of the share loop.

Database location, in priority order:
  1. QUEST_DB_PATH env var (tests point this at a tmp dir)
  2. /data/quests.db when /data exists (the Railway volume mount)
  3. backend/.data/quests.db for local dev (gitignored)

All functions are synchronous; call them from async routes via
fastapi.concurrency.run_in_threadpool.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from models import Quest

# No 0/1/i/l/o lookalikes: these ids get retyped from Instagram stories.
_ALPHABET = "23456789abcdefghjkmnpqrstuvwxyz"
SHORT_ID_LENGTH = 8
_RAILWAY_VOLUME = Path("/data")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS stored_quests (
    short_id TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL UNIQUE,
    quest_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    views INTEGER NOT NULL DEFAULT 0,
    last_viewed_at TEXT
)
"""


@dataclass(frozen=True)
class StoredQuest:
    short_id: str
    quest_json: str
    created_at: str
    views: int


def _db_path() -> Path:
    env = os.environ.get("QUEST_DB_PATH", "").strip()
    if env:
        return Path(env)
    if _RAILWAY_VOLUME.is_dir():
        return _RAILWAY_VOLUME / "quests.db"
    return Path(__file__).resolve().parent / ".data" / "quests.db"


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(_SCHEMA)
    return conn


def _new_short_id() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(SHORT_ID_LENGTH))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def store_quest(quest: Quest) -> str:
    """Persist a quest and return its short id.

    Idempotent per content: re-sharing the same quest (same id, title, stops)
    returns the existing short id instead of inserting a duplicate row. The
    canonical JSON comes from the validated model, so unknown/extra fields in
    the request body are never stored.
    """
    quest_json = quest.model_dump_json()
    content_hash = hashlib.sha256(quest_json.encode("utf-8")).hexdigest()

    with closing(_connect()) as conn, conn:
        row = conn.execute(
            "SELECT short_id FROM stored_quests WHERE content_hash = ?",
            (content_hash,),
        ).fetchone()
        if row is not None:
            return row["short_id"]

        while True:
            short_id = _new_short_id()
            try:
                conn.execute(
                    "INSERT INTO stored_quests"
                    " (short_id, content_hash, quest_json, created_at)"
                    " VALUES (?, ?, ?, ?)",
                    (short_id, content_hash, quest_json, _now_iso()),
                )
                return short_id
            except sqlite3.IntegrityError:
                # Either a short_id collision (retry with a new id) or a
                # concurrent insert of the same content (return its id).
                row = conn.execute(
                    "SELECT short_id FROM stored_quests WHERE content_hash = ?",
                    (content_hash,),
                ).fetchone()
                if row is not None:
                    return row["short_id"]


def fetch_quest(short_id: str, *, count_view: bool = True) -> StoredQuest | None:
    """Look up a stored quest, bumping its view count unless told not to.

    Crawler prefetches (the OG preview function) pass count_view=False so
    views only measure humans opening the link.
    """
    with closing(_connect()) as conn, conn:
        if count_view:
            conn.execute(
                "UPDATE stored_quests SET views = views + 1, last_viewed_at = ?"
                " WHERE short_id = ?",
                (_now_iso(), short_id),
            )
        row = conn.execute(
            "SELECT short_id, quest_json, created_at, views FROM stored_quests"
            " WHERE short_id = ?",
            (short_id,),
        ).fetchone()

    if row is None:
        return None
    return StoredQuest(
        short_id=row["short_id"],
        quest_json=row["quest_json"],
        created_at=row["created_at"],
        views=row["views"],
    )
