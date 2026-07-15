"""Pure-veg mode: food stops require veg-confirmed places, never non-veg ones."""

import asyncio

from models import CostEstimate, Occasion, QuestGenerationRequest
from quest_generator import assemble_quest
from services.nearby_places_service import NearbyPlacesService
from services.places_provider import PlaceHours, RawPlace, ResolvedLocation


def _restaurant(
    provider_id: str,
    name: str,
    *,
    lat: float,
    rating: float,
    ratings_total: int,
    serves_veg: bool | None,
) -> RawPlace:
    return RawPlace(
        provider_id,
        name,
        "Road",
        lat,
        0.0,
        rating,
        ["restaurant"],
        ratings_total,
        "OPERATIONAL",
        serves_vegetarian_food=serves_veg,
    )


class VegMixProvider:
    """One restaurant pool: a top-scored non-veg place, a mid unknown, and a
    weaker-but-confirmed veg place. Everything is verifiably open."""

    def __init__(self, places: list[RawPlace] | None = None) -> None:
        self.places = places or [
            _restaurant(
                "meaty", "Imperial Grill House",
                lat=0.001, rating=4.9, ratings_total=5000, serves_veg=False,
            ),
            _restaurant(
                "unknown", "Riverside Kitchen",
                lat=0.002, rating=4.7, ratings_total=2000, serves_veg=None,
            ),
            _restaurant(
                "veg", "Green Leaf Garden",
                lat=0.003, rating=4.3, ratings_total=400, serves_veg=True,
            ),
        ]

    async def geocode(self, query: str) -> ResolvedLocation:
        return ResolvedLocation(name=query, lat=0.0, lng=0.0)

    async def nearby_by_type(
        self,
        *,
        lat: float,
        lng: float,
        radius_meters: int,
        place_type: str,
        target_count: int | None = None,
    ) -> list[RawPlace]:
        if place_type == "restaurant":
            return self.places
        return []

    async def place_hours(self, *, provider_id: str, weekday: int) -> PlaceHours:
        return PlaceHours("09:00", "23:30", False)


def _request(pure_veg: bool) -> QuestGenerationRequest:
    # A 1-stop date quest: the single stop is the restaurant slot.
    return QuestGenerationRequest(
        location="Test Area",
        occasion=Occasion.date,
        cost_estimate=CostEstimate.mid,
        people=2,
        stop_count=1,
        pure_veg=pure_veg,
    )


def _assemble(provider, pure_veg: bool, monkeypatch):
    async def fake_narrative(**kwargs) -> str:
        return "A test quest."

    monkeypatch.setattr("quest_generator.generate_quest_narrative", fake_narrative)
    service = NearbyPlacesService(provider)
    return asyncio.run(assemble_quest(_request(pure_veg), service))


def test_pure_veg_prefers_confirmed_over_higher_scored_non_veg(monkeypatch) -> None:
    quest = _assemble(VegMixProvider(), pure_veg=True, monkeypatch=monkeypatch)
    assert [s.place.name for s in quest.stops] == ["Green Leaf Garden"]
    # The pick was confirmed veg — no hedging note needed.
    assert quest.veg_note is None


def test_without_pure_veg_scoring_is_unchanged(monkeypatch) -> None:
    quest = _assemble(VegMixProvider(), pure_veg=False, monkeypatch=monkeypatch)
    assert [s.place.name for s in quest.stops] == ["Imperial Grill House"]
    assert quest.veg_note is None


def test_unknown_veg_is_fallback_and_sets_note(monkeypatch) -> None:
    provider = VegMixProvider(
        places=[
            _restaurant(
                "meaty", "Imperial Grill House",
                lat=0.001, rating=4.9, ratings_total=5000, serves_veg=False,
            ),
            _restaurant(
                "unknown", "Riverside Kitchen",
                lat=0.002, rating=4.7, ratings_total=2000, serves_veg=None,
            ),
        ]
    )
    quest = _assemble(provider, pure_veg=True, monkeypatch=monkeypatch)
    # Non-veg is never offered; the unknown is used, with an honest note.
    assert [s.place.name for s in quest.stops] == ["Riverside Kitchen"]
    assert quest.veg_note is not None


def test_pure_veg_name_counts_as_confirmed(monkeypatch) -> None:
    provider = VegMixProvider(
        places=[
            _restaurant(
                "unknown", "Riverside Kitchen",
                lat=0.001, rating=4.9, ratings_total=5000, serves_veg=None,
            ),
            _restaurant(
                "named_veg", "Shudh Ruchulu Pure Veg",
                lat=0.002, rating=4.2, ratings_total=300, serves_veg=None,
            ),
        ]
    )
    quest = _assemble(provider, pure_veg=True, monkeypatch=monkeypatch)
    assert [s.place.name for s in quest.stops] == ["Shudh Ruchulu Pure Veg"]
    assert quest.veg_note is None


def test_pure_veg_never_empties_a_stop_via_unknowns(monkeypatch) -> None:
    provider = VegMixProvider(
        places=[
            _restaurant(
                "unknown", "Riverside Kitchen",
                lat=0.001, rating=4.7, ratings_total=2000, serves_veg=None,
            ),
        ]
    )
    quest = _assemble(provider, pure_veg=True, monkeypatch=monkeypatch)
    assert len(quest.stops) == 1
    assert quest.veg_note is not None
