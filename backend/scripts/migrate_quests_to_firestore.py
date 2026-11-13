"""Copy shared quests from the SQLite store (Railway volume) into Firestore.

Two steps, because the SQLite file lives on Railway and Firestore is reached
with your local gcloud credentials:

1. Export on Railway (prints JSON to stdout, stdlib only):
     railway ssh -- python scripts/migrate_quests_to_firestore.py export /data/quests.db > quests.json

2. Import locally (needs `gcloud auth application-default login`):
     python scripts/migrate_quests_to_firestore.py import quests.json --project YOUR_PROJECT_ID

Import keeps each quest's short id, view count and timestamps, so existing
/q/<id> links keep working. It is safe to re-run: docs that already exist in
Firestore are skipped, so run it once before switching the frontend over and
once more right after to catch links created in between.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from contextlib import closing

QUESTS_COLLECTION = "shared_quests"
HASHES_COLLECTION = "shared_quest_hashes"


def export_rows(db_path: str) -> None:
    with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT short_id, content_hash, quest_json, created_at, views, last_viewed_at"
            " FROM stored_quests ORDER BY created_at"
        ).fetchall()
    json.dump([dict(r) for r in rows], sys.stdout)
    print(f"exported {len(rows)} quests", file=sys.stderr)


def import_rows(json_path: str, project: str | None, database: str) -> None:
    from google.api_core.exceptions import AlreadyExists
    from google.cloud import firestore

    with open(json_path, encoding="utf-8") as fh:
        rows = json.load(fh)

    client = firestore.Client(project=project, database=database)
    created = skipped = 0
    for row in rows:
        quest_ref = client.collection(QUESTS_COLLECTION).document(row["short_id"])
        try:
            quest_ref.create(
                {
                    "content_hash": row["content_hash"],
                    "quest_json": row["quest_json"],
                    "created_at": row["created_at"],
                    "views": int(row.get("views") or 0),
                    "last_viewed_at": row.get("last_viewed_at"),
                }
            )
            created += 1
        except AlreadyExists:
            skipped += 1
        try:
            client.collection(HASHES_COLLECTION).document(row["content_hash"]).create(
                {"short_id": row["short_id"]}
            )
        except AlreadyExists:
            pass
    print(f"imported {created} quests, skipped {skipped} already in Firestore (of {len(rows)})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    exp = sub.add_parser("export", help="dump the SQLite store as JSON to stdout")
    exp.add_argument("db_path")
    imp = sub.add_parser("import", help="write an exported JSON file into Firestore")
    imp.add_argument("json_path")
    imp.add_argument("--project", default=None, help="GCP project id (defaults to gcloud's)")
    imp.add_argument("--database", default="(default)")
    args = parser.parse_args()

    if args.cmd == "export":
        export_rows(args.db_path)
    else:
        import_rows(args.json_path, args.project, args.database)


if __name__ == "__main__":
    main()
