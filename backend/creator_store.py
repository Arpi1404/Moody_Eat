"""Store for creator pages: a public list of quests behind /by/<handle>.

There are no accounts. A creator's private manage link carries a random key,
and the store keeps only its SHA-256 hash, so the key cannot be read back out
of the database: a lost one is replaced, never recovered.

Same two backends as quest_store (QUEST_STORE_BACKEND): a table in the same
SQLite file, or a Firestore collection with one document per handle.

All functions are synchronous; call them from async routes via
fastapi.concurrency.run_in_threadpool.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import sqlite3
from contextlib import closing
from dataclasses import dataclass

import quest_store

CREATORS_COLLECTION = "creator_pages"
MAX_QUESTS = 50

# Lowercase letters, digits and hyphens, 3 to 30, no hyphen at either end.
_HANDLE_RE = re.compile(r"[a-z0-9][a-z0-9-]{1,28}[a-z0-9]")
# Names that could be mistaken for the site itself or for one of its pages.
RESERVED_HANDLES = frozenset(
    {
        "about", "admin", "administrator", "api", "app", "by", "create",
        "creator", "creators", "dev", "explore", "guides", "help", "home",
        "journal", "landing", "login", "manage", "moderator", "moody",
        "moody-eat", "moodyeat", "official", "plan", "privacy", "quest",
        "quests", "results", "root", "saved", "settings", "staff", "support",
        "team", "terms", "www",
    }
)
# 32 random bytes: far beyond guessing.
_KEY_BYTES = 32

_SCHEMA = """
CREATE TABLE IF NOT EXISTS creator_pages (
    handle TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    bio TEXT NOT NULL DEFAULT '',
    instagram TEXT NOT NULL DEFAULT '',
    token_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    quest_ids TEXT NOT NULL DEFAULT '[]',
    views INTEGER NOT NULL DEFAULT 0
)
"""


@dataclass(frozen=True)
class Creator:
    handle: str
    display_name: str
    bio: str
    instagram: str
    token_hash: str
    created_at: str
    # In the order they were added: newest last.
    quest_ids: tuple[str, ...]
    views: int


class HandleTaken(Exception):
    pass


class PageFull(Exception):
    pass


class PageGone(Exception):
    """The page was deleted while a change to it was being made."""


def handle_problem(handle: str) -> str | None:
    """Why a handle cannot be used, or None when it can."""
    if not _HANDLE_RE.fullmatch(handle):
        return (
            "A handle is 3 to 30 characters: lowercase letters, digits and "
            "hyphens, not starting or ending with a hyphen."
        )
    if handle in RESERVED_HANDLES:
        return f"'{handle}' is reserved."
    return None


def _new_token(handle: str) -> str:
    # The handle travels with the secret so the page can be looked up without
    # searching the database by key. It is public, and "." cannot be in one.
    return f"{handle}.{secrets.token_urlsafe(_KEY_BYTES)}"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _firestore() -> bool:
    return quest_store._backend() == "firestore"


# --- What the API and the script use ----------------------------------------


def create_creator(handle: str, display_name: str) -> str:
    """Make a page and return its key. This is the only time the key exists
    outside the creator's hands. Raises HandleTaken, or ValueError for a
    handle that is not allowed."""
    problem = handle_problem(handle)
    if problem:
        raise ValueError(problem)
    token = _new_token(handle)
    record = {
        "display_name": display_name,
        "bio": "",
        "instagram": "",
        "token_hash": _hash(token),
        "created_at": quest_store._now_iso(),
        "quest_ids": [],
        "views": 0,
    }
    if _firestore():
        _firestore_create(handle, record)
    else:
        _sqlite_create(handle, record)
    return token


def get_creator(handle: str, *, count_view: bool = False) -> Creator | None:
    if handle_problem(handle):
        return None
    if _firestore():
        return _firestore_get(handle, count_view=count_view)
    return _sqlite_get(handle, count_view=count_view)


def creator_for_token(token: str) -> Creator | None:
    """The page this key opens, or None for a wrong or replaced key."""
    handle = token.split(".", 1)[0]
    creator = get_creator(handle)
    if creator is None:
        return None
    # Constant time: how long this takes says nothing about the stored hash.
    if not hmac.compare_digest(_hash(token), creator.token_hash):
        return None
    return creator


def update_profile(handle: str, changes: dict[str, str]) -> Creator | None:
    """Change any of display_name, bio and instagram. May raise PageGone."""
    allowed = {k: v for k, v in changes.items() if k in ("display_name", "bio", "instagram")}
    if allowed:
        _update(handle, allowed)
    return get_creator(handle)


def rotate_token(handle: str) -> str | None:
    """Replace the key; the old manage link stops working at once. None when
    there is no such page."""
    if get_creator(handle) is None:
        return None
    token = _new_token(handle)
    try:
        _update(handle, {"token_hash": _hash(token)})
    except PageGone:
        return None
    return token


def add_quest(handle: str, short_id: str) -> bool:
    """Put a quest on the page. False when it was there already or there is no
    such page. Raises PageFull when the page holds MAX_QUESTS, and may raise
    PageGone."""
    if _firestore():
        return _firestore_add(handle, short_id)
    return _sqlite_add(handle, short_id)


def remove_quest(handle: str, short_id: str) -> None:
    """Take a quest off the page. Its share link is not touched."""
    if _firestore():
        _firestore_remove(handle, short_id)
    else:
        _sqlite_remove(handle, short_id)


def delete_creator(handle: str) -> bool:
    if get_creator(handle) is None:
        return False
    if _firestore():
        quest_store.firestore_client().collection(CREATORS_COLLECTION).document(handle).delete()
    else:
        with closing(_connect()) as conn, conn:
            conn.execute("DELETE FROM creator_pages WHERE handle = ?", (handle,))
    return True


def list_creators() -> list[Creator]:
    if _firestore():
        snaps = quest_store.firestore_client().collection(CREATORS_COLLECTION).stream()
        found = [_from_record(snap.id, snap.to_dict()) for snap in snaps]
    else:
        with closing(_connect()) as conn, conn:
            rows = conn.execute("SELECT * FROM creator_pages").fetchall()
        found = [_from_row(row) for row in rows]
    return sorted(found, key=lambda c: c.handle)


# --- SQLite -----------------------------------------------------------------


def _connect() -> sqlite3.Connection:
    path = quest_store._db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(_SCHEMA)
    return conn


def _from_record(handle: str, data: dict) -> Creator:
    return Creator(
        handle=handle,
        display_name=data.get("display_name") or handle,
        bio=data.get("bio") or "",
        instagram=data.get("instagram") or "",
        token_hash=data["token_hash"],
        created_at=data["created_at"],
        quest_ids=tuple(data.get("quest_ids") or ()),
        views=int(data.get("views") or 0),
    )


def _from_row(row: sqlite3.Row) -> Creator:
    data = dict(row)
    data["quest_ids"] = json.loads(data["quest_ids"])
    return _from_record(data["handle"], data)


def _sqlite_create(handle: str, record: dict) -> None:
    with closing(_connect()) as conn, conn:
        try:
            conn.execute(
                "INSERT INTO creator_pages"
                " (handle, display_name, token_hash, created_at)"
                " VALUES (?, ?, ?, ?)",
                (handle, record["display_name"], record["token_hash"], record["created_at"]),
            )
        except sqlite3.IntegrityError as exc:
            raise HandleTaken(handle) from exc


def _sqlite_get(handle: str, *, count_view: bool) -> Creator | None:
    with closing(_connect()) as conn, conn:
        if count_view:
            conn.execute(
                "UPDATE creator_pages SET views = views + 1 WHERE handle = ?", (handle,)
            )
        row = conn.execute(
            "SELECT * FROM creator_pages WHERE handle = ?", (handle,)
        ).fetchone()
    return None if row is None else _from_row(row)


def _update(handle: str, changes: dict[str, str]) -> None:
    """Set plain fields. The names come from this module, never from a caller
    of the API. Raises PageGone when there is no such page."""
    if _firestore():
        _firestore_change(_document(handle), changes)
        return
    columns = ", ".join(f"{name} = ?" for name in changes)
    with closing(_connect()) as conn, conn:
        changed = conn.execute(
            f"UPDATE creator_pages SET {columns} WHERE handle = ?",
            (*changes.values(), handle),
        ).rowcount
    if not changed:
        raise PageGone


def _sqlite_change_quests(handle: str, change) -> bool:
    """Read, change and write the quest list under one write lock, so two
    additions at once cannot lose one or overfill the page."""
    with closing(_connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT quest_ids FROM creator_pages WHERE handle = ?", (handle,)
            ).fetchone()
            if row is None:
                conn.rollback()
                return False
            before = json.loads(row["quest_ids"])
            after = change(list(before))
            if after != before:
                conn.execute(
                    "UPDATE creator_pages SET quest_ids = ? WHERE handle = ?",
                    (json.dumps(after), handle),
                )
            conn.commit()
            return after != before
        except BaseException:
            conn.rollback()
            raise


def _sqlite_add(handle: str, short_id: str) -> bool:
    def change(ids: list[str]) -> list[str]:
        if short_id in ids:
            return ids
        if len(ids) >= MAX_QUESTS:
            raise PageFull(handle)
        return [*ids, short_id]

    return _sqlite_change_quests(handle, change)


def _sqlite_remove(handle: str, short_id: str) -> None:
    _sqlite_change_quests(handle, lambda ids: [i for i in ids if i != short_id])


# --- Firestore --------------------------------------------------------------


def _document(handle: str):
    return quest_store.firestore_client().collection(CREATORS_COLLECTION).document(handle)


def _firestore_create(handle: str, record: dict) -> None:
    from google.api_core.exceptions import AlreadyExists

    try:
        _document(handle).create(record)
    except AlreadyExists as exc:
        raise HandleTaken(handle) from exc


def _firestore_get(handle: str, *, count_view: bool) -> Creator | None:
    from google.api_core.exceptions import NotFound
    from google.cloud import firestore

    ref = _document(handle)
    if count_view:
        try:
            ref.update({"views": firestore.Increment(1)})
        except NotFound:
            return None
    snap = ref.get()
    return _from_record(handle, snap.to_dict()) if snap.exists else None


def _firestore_change(ref, changes: dict) -> None:
    """Update a page's document. Raises PageGone when it no longer exists."""
    from google.api_core.exceptions import NotFound

    try:
        ref.update(changes)
    except NotFound as exc:
        raise PageGone from exc


def _firestore_add(handle: str, short_id: str) -> bool:
    from google.cloud import firestore

    creator = _firestore_get(handle, count_view=False)
    if creator is None or short_id in creator.quest_ids:
        return False
    if len(creator.quest_ids) >= MAX_QUESTS:
        raise PageFull(handle)
    ref = _document(handle)
    # An atomic append, so additions made at the same moment are both kept.
    _firestore_change(ref, {"quest_ids": firestore.ArrayUnion([short_id])})
    stored = ref.get().to_dict()
    if stored is None:
        raise PageGone
    # Two at once on a nearly full page could both get in: check after, and
    # step back out rather than leave the page over its limit.
    if len(stored.get("quest_ids") or []) > MAX_QUESTS:
        _firestore_change(ref, {"quest_ids": firestore.ArrayRemove([short_id])})
        raise PageFull(handle)
    return True


def _firestore_remove(handle: str, short_id: str) -> None:
    from google.api_core.exceptions import NotFound
    from google.cloud import firestore

    try:
        _document(handle).update({"quest_ids": firestore.ArrayRemove([short_id])})
    except NotFound:
        pass
