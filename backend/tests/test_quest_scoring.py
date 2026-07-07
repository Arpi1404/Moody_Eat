import asyncio
from datetime import time

from models import CostEstimate, Occasion, PlaceItem, QuestGenerationRequest
from quest_generator import (
    _hours_reject_rule,
    _mood_reject_rule,
    _pick,
    _score_breakdown,
    _why,
    assemble_quest,
)
from services.nearby_places_service import NearbyPlacesService
from services.places_provider import PlaceHours, RawPlace, ResolvedLocation


def _place(
    provider_id: str,
    name: str,
    *,
    rating: float = 4.5,
    reviews: int = 400,
    price_level: int | None = None,
    lat: float = 0.0,
    lng: float = 0.0,
    types: list[str] | None = None,
) -> PlaceItem:
    return PlaceItem(
        name=name,
        address="Test Road",
        lat=lat,
        lng=lng,
        distance_meters=0,
        rating=rating,
        user_ratings_total=reviews,
        price_level=price_level,
        types=types or ["restaurant"],
        provider_id=provider_id,
    )


def test_budget_changes_pick_when_price_levels_differ() -> None:
    cheap_fit = _place(
        "cheap",
        "Budget Hero",
        rating=4.4,
        reviews=500,
        price_level=1,
    )
    splurge_fit = _place(
        "splurge",
        "Premium Room",
        rating=4.9,
        reviews=1000,
        price_level=3,
    )
    candidates = [cheap_fit, splurge_fit]

    cheap_pick = _pick(candidates, CostEstimate.cheap, None, None, set())
    splurge_pick = _pick(candidates, CostEstimate.splurge, None, None, set())

    assert cheap_pick == cheap_fit
    assert splurge_pick == splurge_fit


def test_unknown_price_has_lower_confidence_than_known_price() -> None:
    known = _place("known", "Known Mid", price_level=2)
    unknown = _place("unknown", "Unknown Price", price_level=None)

    known_score = _score_breakdown(known, CostEstimate.mid, None, None)
    unknown_score = _score_breakdown(unknown, CostEstimate.mid, None, None)

    assert known_score.price_source == "google_price_level"
    assert unknown_score.price_source == "unknown"
    assert known_score.confidence > unknown_score.confidence
    assert known_score.total > unknown_score.total


def test_price_mismatch_can_outweigh_nearby_high_rating_for_cheap_budget() -> None:
    nearby_expensive = _place(
        "nearby_expensive",
        "Nearby Premium",
        rating=5.0,
        reviews=1200,
        price_level=4,
        lat=0.0,
        lng=0.001,
    )
    farther_cheap = _place(
        "farther_cheap",
        "Farther Budget",
        rating=4.3,
        reviews=250,
        price_level=1,
        lat=0.0,
        lng=0.012,
    )

    picked = _pick(
        [nearby_expensive, farther_cheap],
        CostEstimate.cheap,
        0.0,
        0.0,
        set(),
    )

    assert picked == farther_cheap


def test_why_does_not_prefix_first_word_of_place_name() -> None:
    place = _place(
        "escape_room",
        "Lock N Escape - Mystery Escape Room Games Hyderabad",
        rating=4.8,
        reviews=1200,
    )

    why = _why(place, CostEstimate.mid, 400)

    assert why == "Rated 4.8★ by locals, just a short walk away."
    assert not why.startswith("Lock —")


def test_why_falls_back_to_clean_sentence() -> None:
    place = _place("plain", "Karachi Bakery", rating=4.0, reviews=120)

    why = _why(place, CostEstimate.mid, None)

    assert why == "A solid local choice."
    assert not why.startswith("Karachi —")


def test_hours_reject_rule_requires_slot_to_fit_inside_opening_window() -> None:
    open_place = _place("open", "Open Cafe").model_copy(update={
        "opens_today": "18:00",
        "closes_today": "23:00",
    })
    closed_place = _place("closed", "Closed Cafe").model_copy(update={
        "opens_today": "09:00",
        "closes_today": "13:00",
    })
    unknown_place = _place("unknown", "Unknown Hours Cafe")

    assert _hours_reject_rule(open_place, time(19, 0), time(20, 0)) is None
    assert _hours_reject_rule(closed_place, time(19, 0), time(20, 0)) == "hours_closed"
    assert _hours_reject_rule(unknown_place, time(19, 0), time(20, 0)) == "hours_unknown"


def test_mood_reject_rule_blocks_evening_worship_and_date_escape_rooms() -> None:
    temple = _place(
        "temple",
        "Peace Temple",
        types=["tourist_attraction", "place_of_worship"],
    )
    escape_room = _place(
        "escape",
        "Lock N Escape - Mystery Escape Room Games Hyderabad",
        types=["tourist_attraction"],
    )

    assert _mood_reject_rule(temple, Occasion.date, time(20, 0)) == "mood_type"
    assert _mood_reject_rule(temple, Occasion.friends, time(20, 0)) == "mood_type"
    assert _mood_reject_rule(escape_room, Occasion.date, time(20, 0)) == "mood_name"
    assert _mood_reject_rule(escape_room, Occasion.friends, time(20, 0)) is None


class QuestViabilityProvider:
    def __init__(self) -> None:
        self.hours_requested: list[str] = []

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
        by_type = {
            "restaurant": [
                RawPlace("closed_rest", "Closed Fancy Room", "Road", 0.001, 0.0, 5.0, ["restaurant"], 1200),
                RawPlace("open_rest", "Open Date Bistro", "Road", 0.002, 0.0, 4.5, ["restaurant"], 600),
            ],
            "bakery": [
                RawPlace("bakery", "Late Bakery", "Road", 0.003, 0.0, 4.4, ["bakery"], 600),
            ],
            "tourist_attraction": [
                RawPlace("worship", "ISKCON Temple", "Road", 0.004, 0.0, 4.9, ["tourist_attraction", "place_of_worship"], 2000),
                RawPlace("escape", "Lock N Escape - Mystery Escape Room Games Hyderabad", "Road", 0.005, 0.0, 4.8, ["tourist_attraction"], 1400),
            ],
            "park": [
                RawPlace("park", "Open Garden", "Road", 0.006, 0.0, 4.4, ["park"], 700),
            ],
        }
        return by_type.get(place_type, [])

    async def place_hours(
        self,
        *,
        provider_id: str,
        weekday: int,
    ) -> PlaceHours:
        self.hours_requested.append(provider_id)
        hours = {
            "closed_rest": PlaceHours("09:00", "13:00", False),
            "open_rest": PlaceHours("18:00", "23:00", False),
            "bakery": PlaceHours("08:00", "23:30", False),
            "worship": PlaceHours("04:30", "23:00", False),
            "escape": PlaceHours("10:00", "23:00", False),
            "park": PlaceHours("06:00", "22:30", False),
        }
        return hours[provider_id]


def test_assemble_quest_skips_closed_and_mood_wrong_candidates(monkeypatch) -> None:
    async def fake_narrative(**kwargs) -> str:
        return "A test date quest."

    monkeypatch.setattr("quest_generator.generate_quest_narrative", fake_narrative)
    provider = QuestViabilityProvider()
    service = NearbyPlacesService(provider)
    req = QuestGenerationRequest(
        location="Govindpuram",
        occasion=Occasion.date,
        cost_estimate=CostEstimate.mid,
        people=2,
        duration_hours=3.0,
    )

    quest = asyncio.run(assemble_quest(req, service))

    names = [stop.place.name for stop in quest.stops]
    assert names == ["Open Date Bistro", "Late Bakery", "Open Garden"]
    assert "closed_rest" in provider.hours_requested
    assert "worship" not in provider.hours_requested
    assert "escape" not in provider.hours_requested
