"""Creator pages: the public list behind /by/<handle>, and the creator's own
view of it, opened with the key in their private manage link.

Pages are made by the team with scripts/creator_page.py. There is no sign-up
route here, and there are no accounts, cookies or passwords.

The key arrives as `Authorization: Bearer <token>`. It must not reach error
reports. Naming a variable `token` is not enough: scrubbing goes by variable
name, and the request's `scope`, a local in the framework's own frames, holds
the header inside a list. So main.py turns off the capture of local variables.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

import creator_store
from creator_store import MAX_QUESTS, Creator, PageFull, PageGone
from models import tidy_text
from quest_store import StoredQuest, fetch_quests

router = APIRouter()

CREATOR_NAME_MAX = 40
CREATOR_BIO_MAX = 140
# Instagram's own rules: letters, digits, "_" and ".", no ".." and no "." at
# either end. Nothing that matches can be anything but a username in a URL.
_INSTAGRAM_RE = re.compile(r"(?!\.)(?!.*\.\.)[A-Za-z0-9._]{1,30}(?<!\.)")
_SHORT_ID_PATTERN = r"^[a-z0-9]{4,16}$"


class CreatorQuestStop(BaseModel):
    name: str
    # The note the quest's maker typed; None for automatic lines.
    note: Optional[str] = None


class CreatorQuest(BaseModel):
    """A quest as a creator page lists it: titles, stop names and typed words.

    No ratings, hours or prices: a stored quest is a snapshot, and those go
    out of date.
    """

    short_id: str
    title: str
    # A page may list quests other people made.
    made_by: Optional[str] = None
    intro: Optional[str] = None
    stops: list[CreatorQuestStop]


class MyQuest(CreatorQuest):
    # How many times the share link has been opened. Only the owner sees it.
    opens: int
    # False once the quest has been taken down.
    available: bool = True


class CreatorProfile(BaseModel):
    handle: str
    display_name: str
    bio: str
    instagram: str


class PublicCreatorPage(CreatorProfile):
    quests: list[CreatorQuest]


class MyCreatorPage(CreatorProfile):
    page_views: int
    max_quests: int
    quests: list[MyQuest]


class AddQuestRequest(BaseModel):
    short_id: str = Field(pattern=_SHORT_ID_PATTERN)


class AddQuestResult(BaseModel):
    # False when the quest was on the page already.
    added: bool
    page: MyCreatorPage


class ProfileChanges(BaseModel):
    """Only the fields sent are changed. The limits here are generous; the real
    ones are checked in the route, which can answer in plain words."""

    display_name: Optional[str] = Field(default=None, max_length=500)
    bio: Optional[str] = Field(default=None, max_length=2000)
    instagram: Optional[str] = Field(default=None, max_length=500)


def _summary(stored: StoredQuest) -> CreatorQuest:
    """Read a stored quest defensively: old ones are never revalidated."""
    quest = json.loads(stored.quest_json)
    stops = []
    for stop in quest.get("stops") or []:
        note = tidy_text(str(stop.get("why_this_place") or ""))
        stops.append(
            CreatorQuestStop(
                name=tidy_text(str((stop.get("place") or {}).get("name") or "")),
                note=note if stop.get("note_by_creator") and note else None,
            )
        )
    intro = tidy_text(str(quest.get("narrative") or ""))
    return CreatorQuest(
        short_id=stored.short_id,
        title=tidy_text(str(quest.get("title") or "")) or "Untitled quest",
        made_by=tidy_text(str(quest.get("created_by") or "")) or None,
        intro=intro if quest.get("narrative_by_creator") and intro else None,
        stops=stops,
    )


def _profile(creator: Creator) -> dict:
    return {
        "handle": creator.handle,
        "display_name": creator.display_name,
        "bio": creator.bio,
        "instagram": creator.instagram,
    }


def _newest_first(creator: Creator) -> list[str]:
    return list(reversed(creator.quest_ids))


def _public_page(creator: Creator) -> PublicCreatorPage:
    ids = _newest_first(creator)
    stored = fetch_quests(ids)
    return PublicCreatorPage(
        **_profile(creator),
        # Taken-down quests simply are not listed.
        quests=[_summary(stored[i]) for i in ids if i in stored],
    )


def _my_page(creator: Creator) -> MyCreatorPage:
    ids = _newest_first(creator)
    stored = fetch_quests(ids)
    quests = [
        MyQuest(**_summary(stored[i]).model_dump(), opens=stored[i].views)
        if i in stored
        # Shown so the owner can clear it: it still takes up a place.
        else MyQuest(short_id=i, title="Removed quest", stops=[], opens=0, available=False)
        for i in ids
    ]
    return MyCreatorPage(
        **_profile(creator),
        page_views=creator.views,
        max_quests=MAX_QUESTS,
        quests=quests,
    )


def _fail(status: int, code: str, message: str, **kwargs) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message}, **kwargs)


async def signed_in_creator(
    response: Response,
    authorization: Optional[str] = Header(default=None),
) -> Creator:
    scheme, _, token = (authorization or "").partition(" ")
    token = token.strip()
    creator = None
    if scheme.lower() == "bearer" and token:
        creator = await run_in_threadpool(creator_store.creator_for_token, token)
    if creator is None:
        raise _fail(
            401,
            "bad_key",
            "This manage link doesn't work. It may have been replaced with a new one.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    response.headers["Cache-Control"] = "no-store"
    return creator


def _page_gone() -> HTTPException:
    return _fail(404, "creator_not_found", "This page no longer exists.")


async def _reload_my_page(handle: str) -> MyCreatorPage:
    creator = await run_in_threadpool(creator_store.get_creator, handle)
    if creator is None:
        raise _page_gone()
    return await run_in_threadpool(_my_page, creator)


@router.get("/api/creators/{handle}", response_model=PublicCreatorPage)
async def get_creator_page(
    handle: str = Path(max_length=64),
    count_view: bool = Query(default=True),
) -> PublicCreatorPage:
    """A creator's public page. Counts a view of the page, never of a quest."""
    creator = await run_in_threadpool(
        creator_store.get_creator, handle.strip().lower(), count_view=count_view
    )
    if creator is None:
        # `code` tells this apart from the plain 404 of a backend without
        # creator pages.
        raise _fail(404, "creator_not_found", "There is no creator page here.")
    return await run_in_threadpool(_public_page, creator)


@router.get("/api/creator/me", response_model=MyCreatorPage)
async def get_my_page(creator: Creator = Depends(signed_in_creator)) -> MyCreatorPage:
    return await run_in_threadpool(_my_page, creator)


@router.patch("/api/creator/me", response_model=MyCreatorPage)
async def edit_my_page(
    changes: ProfileChanges,
    creator: Creator = Depends(signed_in_creator),
) -> MyCreatorPage:
    update: dict[str, str] = {}
    if changes.display_name is not None:
        name = tidy_text(changes.display_name)
        if not 1 <= len(name) <= CREATOR_NAME_MAX:
            raise _fail(422, "bad_name", f"Your name needs 1 to {CREATOR_NAME_MAX} characters.")
        update["display_name"] = name
    if changes.bio is not None:
        bio = tidy_text(changes.bio)
        if len(bio) > CREATOR_BIO_MAX:
            raise _fail(422, "bad_bio", f"Keep your bio to {CREATOR_BIO_MAX} characters.")
        update["bio"] = bio
    if changes.instagram is not None:
        username = changes.instagram.strip().removeprefix("@")
        if username and not _INSTAGRAM_RE.fullmatch(username):
            raise _fail(
                422, "bad_instagram", "Enter just your Instagram username, like priya.eats."
            )
        update["instagram"] = username
    try:
        await run_in_threadpool(creator_store.update_profile, creator.handle, update)
    except PageGone as exc:
        raise _page_gone() from exc
    return await _reload_my_page(creator.handle)


@router.post("/api/creator/me/quests", response_model=AddQuestResult)
async def add_to_my_page(
    body: AddQuestRequest,
    creator: Creator = Depends(signed_in_creator),
) -> AddQuestResult:
    if not await run_in_threadpool(fetch_quests, [body.short_id]):
        raise _fail(
            404,
            "quest_not_found",
            "There is no quest at that link. Share the quest again and paste the new link.",
        )
    try:
        added = await run_in_threadpool(creator_store.add_quest, creator.handle, body.short_id)
    except PageFull as exc:
        raise _fail(
            409,
            "page_full",
            f"Your page has {MAX_QUESTS} quests, the most it can hold. "
            "Remove one to add another.",
        ) from exc
    except PageGone as exc:
        raise _page_gone() from exc
    return AddQuestResult(added=added, page=await _reload_my_page(creator.handle))


@router.delete("/api/creator/me/quests/{short_id}", response_model=MyCreatorPage)
async def remove_from_my_page(
    short_id: str = Path(pattern=_SHORT_ID_PATTERN),
    creator: Creator = Depends(signed_in_creator),
) -> MyCreatorPage:
    """Takes the quest off the page only; its share link keeps working."""
    await run_in_threadpool(creator_store.remove_quest, creator.handle, short_id)
    return await _reload_my_page(creator.handle)
