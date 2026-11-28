"""Hand-curated quests served from the home page — eight per city.

The quests themselves live in `curated/<city>.py`; this module is the
registry the API, the verifier and the guide export read from.

Adding a city
-------------
1. Write `curated/<city>.py` with a `QUESTS` list (see `curated/builders.py`).
   `python -m scripts.lookup_place "<venue>, <area>, <city>"` prints a
   ready-to-paste `place(...)` with the real Google Place ID.
2. Register it in `CURATED_CITIES` below and in the frontend's
   `src/lib/cities.ts`.
3. `python -m scripts.verify_curated --city <key>` must pass, then refresh the
   guide snapshot with `python -m scripts.export_curated`.

Curation rules (enforced by tests/test_curated_quests.py and the verifier):
    * Exactly eight quests per city: three date, three friends, one solo, one
      family. At least one friends quest has no brewery or bar stop, and at
      least one date does not start in the early evening.
    * No venue appears twice within a city.
    * No place rated under 4.0, none permanently closed.
    * Each `why_this_place` justifies *this* venue over nearby alternatives.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from curated import bangalore, gurgaon, hyderabad
from models import Quest

QUESTS_PER_CITY = 8


def _curated(quests: list[Quest]) -> list[Quest]:
    """The city's quests, marked as hand-made rather than generated."""
    return [quest.model_copy(update={"origin": "curated"}) for quest in quests]


@dataclass(frozen=True)
class CuratedCity:
    key: str
    name: str
    # City centre. The frontend decides which city a visitor is nearest to;
    # here it only bounds the content checks ("is this stop really in town?").
    lat: float
    lng: float
    # Other names the same city goes by, lowercase.
    aliases: tuple[str, ...]
    quests: list[Quest]


CURATED_CITIES: tuple[CuratedCity, ...] = (
    CuratedCity(
        key="hyderabad",
        name="Hyderabad",
        lat=17.385,
        lng=78.4867,
        aliases=("secunderabad", "cyberabad"),
        quests=_curated(hyderabad.QUESTS),
    ),
    CuratedCity(
        key="bangalore",
        name="Bangalore",
        lat=12.9716,
        lng=77.5946,
        aliases=("bengaluru",),
        quests=_curated(bangalore.QUESTS),
    ),
    CuratedCity(
        key="gurgaon",
        name="Gurgaon",
        lat=28.4595,
        lng=77.0266,
        aliases=("gurugram",),
        quests=_curated(gurgaon.QUESTS),
    ),
)

_CITY_BY_NAME: dict[str, CuratedCity] = {
    name: city for city in CURATED_CITIES for name in (city.key, *city.aliases)
}

# Keyed by city key only — what the verifier and the export iterate over.
CURATED_QUESTS: dict[str, list[Quest]] = {city.key: city.quests for city in CURATED_CITIES}

_QUEST_BY_ID: dict[uuid.UUID, Quest] = {
    quest.id: quest for city in CURATED_CITIES for quest in city.quests
}


def find_city(name: str) -> CuratedCity | None:
    """The curated city called `name` (key or alias, any case), if any."""
    return _CITY_BY_NAME.get(name.strip().lower())


def find_quest(quest_id: uuid.UUID) -> Quest | None:
    return _QUEST_BY_ID.get(quest_id)
