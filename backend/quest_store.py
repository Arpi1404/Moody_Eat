"""Store for shared quests (short links).

Shared quests otherwise live only in the creator's browser, so share links
had to carry the whole quest in an 800-char #q= fragment. Storing the quest
server-side gives moodyeat.in/q/<short_id> links, per-quest OG previews for
crawlers, and a view count — the receiving side of the share loop.

Two backends, picked by QUEST_STORE_BACKEND:

* ``sqlite`` (default): a local file. Fine on a host with a persistent disk
  (Railway volume) and for local dev. Location, in priority order:
    1. QUEST_DB_PATH env var (tests point this at a tmp dir)
    2. /data/quests.db when /data exists (the Railway volume mount)
    3. backend/.data/quests.db for local dev (gitignored)
* ``firestore``: Google Cloud Firestore. Required on Cloud Run, whose disk is
  wiped on every restart. Uses Application Default Credentials; optional
  FIRESTORE_PROJECT and FIRESTORE_DATABASE (default "(default)").

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
from functools import lru_cache
from pathlib import Path
from typing import Any

from models import Quest

# No 0/1/i/l/o lookalikes: these ids get retyped from Instagram stories.
_ALPHABET = "23456789abcdefghjkmnpqrstuvwxyz"
SHORT_ID_LENGTH = 8
_RAILWAY_VOLUME = Path("/data")

# Firestore layout: one doc per quest keyed by short id, plus one doc per
# content hash so re-sharing identical content is idempotent. Both are written
# with create(), which fails if the doc exists — that is the uniqueness check.
QUESTS_COLLECTION = "shared_quests"
HASHES_COLLECTION = "shared_quest_hashes"

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


def _backend() -> str:
    return os.environ.get("QUEST_STORE_BACKEND", "sqlite").strip().lower() or "sqlite"


def _new_short_id() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(SHORT_ID_LENGTH))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canonical(quest: Quest) -> tuple[str, str]:
    """Canonical JSON from the validated model (unknown request fields are
    never stored) and its content hash."""
    quest_json = quest.model_dump_json()
    return quest_json, hashlib.sha256(quest_json.encode("utf-8")).hexdigest()


def store_quest(quest: Quest) -> str:
    """Persist a quest and return its short id.

    Idempotent per content: re-sharing the same quest (same id, title, stops)
    returns the existing short id instead of inserting a duplicate.
    """
    quest_json, content_hash = _canonical(quest)
    if _backend() == "firestore":
        return _firestore_store(quest_json, content_hash)
    return _sqlite_store(quest_json, content_hash)


def fetch_quest(short_id: str, *, count_view: bool = True) -> StoredQuest | None:
    """Look up a stored quest, bumping its view count unless told not to.

    Crawler prefetches (the OG preview function) pass count_view=False so
    views only measure humans opening the link.
    """
    if _backend() == "firestore":
        return _firestore_fetch(short_id, count_view=count_view)
    return _sqlite_fetch(short_id, count_view=count_view)


def delete_quest(short_id: str) -> bool:
    """Take a shared quest down for good. False when there is no such quest.

    Used by scripts/delete_shared_quest.py; no HTTP route reaches it.
    """
    if _backend() == "firestore":
        return _firestore_delete(short_id)
    return _sqlite_delete(short_id)


def describe_store() -> str:
    """Which store the environment points at, in words, for scripts to show."""
    if _backend() == "firestore":
        project = os.environ.get("FIRESTORE_PROJECT", "").strip() or "default project"
        database = os.environ.get("FIRESTORE_DATABASE", "").strip() or "(default)"
        return f"Firestore ({project}, database {database})"
    return f"SQLite file {_db_path()}"


# --- SQLite ---------------------------------------------------------------


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


def _sqlite_store(quest_json: str, content_hash: str) -> str:
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


def _sqlite_fetch(short_id: str, *, count_view: bool) -> StoredQuest | None:
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


def _sqlite_delete(short_id: str) -> bool:
    with closing(_connect()) as conn, conn:
        cursor = conn.execute(
            "DELETE FROM stored_quests WHERE short_id = ?", (short_id,)
        )
        return cursor.rowcount > 0


# --- Firestore ------------------------------------------------------------


@lru_cache
def firestore_client() -> Any:
    """Process-wide Firestore client (tests monkeypatch this)."""
    from google.cloud import firestore

    project = os.environ.get("FIRESTORE_PROJECT", "").strip() or None
    database = os.environ.get("FIRESTORE_DATABASE", "").strip() or "(default)"
    return firestore.Client(project=project, database=database)


def _firestore_store(quest_json: str, content_hash: str) -> str:
    from google.api_core.exceptions import AlreadyExists

    client = firestore_client()
    hash_ref = client.collection(HASHES_COLLECTION).document(content_hash)
    existing = hash_ref.get()
    if existing.exists:
        return existing.to_dict()["short_id"]

    while True:
        short_id = _new_short_id()
        quest_ref = client.collection(QUESTS_COLLECTION).document(short_id)
        try:
            quest_ref.create(
                {
                    "content_hash": content_hash,
                    "quest_json": quest_json,
                    "created_at": _now_iso(),
                    "views": 0,
                    "last_viewed_at": None,
                }
            )
            break
        except AlreadyExists:
            continue  # short_id collision: pick another

    try:
        hash_ref.create({"short_id": short_id})
    except AlreadyExists:
        # A concurrent request stored the same content first: keep theirs.
        quest_ref.delete()
        return hash_ref.get().to_dict()["short_id"]
    return short_id


def _firestore_fetch(short_id: str, *, count_view: bool) -> StoredQuest | None:
    from google.api_core.exceptions import NotFound
    from google.cloud import firestore

    ref = firestore_client().collection(QUESTS_COLLECTION).document(short_id)
    if count_view:
        try:
            ref.update({"views": firestore.Increment(1), "last_viewed_at": _now_iso()})
        except NotFound:
            return None
    snap = ref.get()
    if not snap.exists:
        return None
    data = snap.to_dict()
    return StoredQuest(
        short_id=short_id,
        quest_json=data["quest_json"],
        created_at=data["created_at"],
        views=int(data.get("views") or 0),
    )


def _firestore_delete(short_id: str) -> bool:
    client = firestore_client()
    quest_ref = client.collection(QUESTS_COLLECTION).document(short_id)
    snap = quest_ref.get()
    if not snap.exists:
        return False
    content_hash = snap.to_dict().get("content_hash")
    if content_hash:
        # Left behind, this would hand the dead id to anyone sharing the same
        # content again. It goes first so that stopping halfway is harmless.
        hash_ref = client.collection(HASHES_COLLECTION).document(content_hash)
        pointer = hash_ref.get()
        if pointer.exists and pointer.to_dict().get("short_id") == short_id:
            hash_ref.delete()
    quest_ref.delete()
    return True
