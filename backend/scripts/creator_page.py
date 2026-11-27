"""Create and look after creator pages (/by/<handle>). The team's tool: there
is no public sign-up.

Usage
-----
    cd backend
    python -m scripts.creator_page create --handle priya --name "Priya"
    python -m scripts.creator_page rotate --handle priya
    python -m scripts.creator_page delete --handle priya [--yes]
    python -m scripts.creator_page list

`create` and `rotate` print the private manage link once. It is the only key
to the page and cannot be shown again: send it to the creator privately.

It works on whichever store the environment points at, exactly as the API
does: the local SQLite file by default. For the live site:

    gcloud auth application-default login
    QUEST_STORE_BACKEND=firestore FIRESTORE_PROJECT=<project> \\
        python -m scripts.creator_page list

`--site` (or SITE_URL) sets the address the links are printed for.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import creator_store  # noqa: E402
from creator_routes import CREATOR_NAME_MAX  # noqa: E402
from models import tidy_text  # noqa: E402
from quest_store import describe_store  # noqa: E402

_DEFAULT_SITE = "https://www.moodyeat.in"


def _print_links(site: str, handle: str, token: str) -> None:
    print(f"\nPublic page (for the creator's bio):\n  {site}/by/{handle}")
    print(
        "\nPrivate manage link. It is the key to the page and is shown only now."
        "\nSend it to the creator privately:\n"
        f"  {site}/manage#k={token}"
    )


def _create(args: argparse.Namespace) -> int:
    name = tidy_text(args.name)
    if not 1 <= len(name) <= CREATOR_NAME_MAX:
        print(f"The name needs 1 to {CREATOR_NAME_MAX} characters.", file=sys.stderr)
        return 2
    try:
        token = creator_store.create_creator(args.handle, name)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    except creator_store.HandleTaken:
        print(f"'{args.handle}' is taken. Use rotate for a new link.", file=sys.stderr)
        return 1
    print(f"Created the page for {name}.")
    _print_links(args.site, args.handle, token)
    return 0


def _rotate(args: argparse.Namespace) -> int:
    token = creator_store.rotate_token(args.handle)
    if token is None:
        print(f"No page '{args.handle}'.", file=sys.stderr)
        return 1
    print("The old manage link no longer works.")
    _print_links(args.site, args.handle, token)
    return 0


def _delete(args: argparse.Namespace) -> int:
    creator = creator_store.get_creator(args.handle)
    if creator is None:
        print(f"No page '{args.handle}'.", file=sys.stderr)
        return 1
    print(
        f"{creator.handle}: {tidy_text(creator.display_name)}, "
        f"{len(creator.quest_ids)} quests, {creator.views} page views"
    )
    if not args.yes:
        answer = input("Delete this page? This cannot be undone. [y/N] ")
        if answer.strip().lower() not in ("y", "yes"):
            print("Kept.")
            return 1
    creator_store.delete_creator(creator.handle)
    print(
        "Page deleted. The quests' own share links still work; remove any of "
        "them with scripts.delete_shared_quest."
    )
    return 0


def _list(args: argparse.Namespace) -> int:
    creators = creator_store.list_creators()
    if not creators:
        print("No creator pages.")
        return 0
    print(f"{'handle':<31}{'quests':>7}{'views':>7}  {'created':<12}name")
    for c in creators:
        print(
            f"{c.handle:<31}{len(c.quest_ids):>7}{c.views:>7}  "
            f"{c.created_at[:10]:<12}{tidy_text(c.display_name)}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage creator pages.")
    parser.add_argument(
        "--site", default=os.environ.get("SITE_URL", "").strip() or _DEFAULT_SITE
    )
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="make a page and print its links")
    create.add_argument("--handle", required=True)
    create.add_argument("--name", required=True)
    create.set_defaults(run=_create)
    rotate = commands.add_parser("rotate", help="replace a lost or leaked manage link")
    rotate.add_argument("--handle", required=True)
    rotate.set_defaults(run=_rotate)
    delete = commands.add_parser("delete", help="remove a page")
    delete.add_argument("--handle", required=True)
    delete.add_argument("--yes", action="store_true", help="do not ask first")
    delete.set_defaults(run=_delete)
    commands.add_parser("list", help="show every page").set_defaults(run=_list)

    args = parser.parse_args(argv)
    args.site = args.site.rstrip("/")
    print(f"Store: {describe_store()}")
    return args.run(args)


if __name__ == "__main__":
    raise SystemExit(main())
