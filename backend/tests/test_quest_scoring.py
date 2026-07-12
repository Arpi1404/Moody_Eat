import asyncio
import random
from datetime import time

from models import CostEstimate, Occasion, PlaceItem, QuestGenerationRequest
from quest_generator import (
    _hours_reject_rule,
    _mood_reject_rule,
    _pick,
    _score_breakdown,
    _variety_shuffle,
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
    range_start: int | None = None,
    range_end: int | None = None,
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
        price_range_start_inr=range_start,
        price_range_end_inr=range_end,
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


def test_budget_changes_pick_with_only_inr_price_ranges() -> None:
    """Places API (New) often has priceRange but no priceLevel — budget must still bite."""
    cheap_eats = _place("cheap_eats", "Everyday Tiffin Room", rating=4.4, reviews=500,
                        range_start=150, range_end=300)
    pricey_room = _place("pricey_room", "Tasting Menu Room", rating=4.8, reviews=900,
                         range_start=1500, range_end=2500)
    candidates = [cheap_eats, pricey_room]

    assert _pick(candidates, CostEstimate.cheap, None, None, set()) == cheap_eats
    assert _pick(candidates, CostEstimate.splurge, None, None, set()) == pricey_room


def test_budget_changes_pick_with_only_name_heuristics() -> None:
    """With zero Google price data, the dhaba/lounge name signal still separates tiers."""
    dhaba = _place("dhaba", "National Highway Dhaba", rating=4.4, reviews=500)
    lounge = _place("lounge", "Altitude Lounge", rating=4.6, reviews=700)
    candidates = [dhaba, lounge]

    assert _pick(candidates, CostEstimate.cheap, None, None, set()) == dhaba
    assert _pick(candidates, CostEstimate.splurge, None, None, set()) == lounge


def test_heuristic_price_has_lower_confidence_than_google_data() -> None:
    google_priced = _place("google", "Known Mid", price_level=2)
    heuristic = _place("heuristic", "Midtown Pub", types=["pub", "bar"])

    google_score = _score_breakdown(google_priced, CostEstimate.mid, None, None)
    heuristic_score = _score_breakdown(heuristic, CostEstimate.mid, None, None)

    assert google_score.price_source == "google_price_level"
    assert heuristic_score.price_source == "heuristic"
    assert google_score.confidence > heuristic_score.confidence


def test_variety_shuffle_is_seeded_and_respects_quality_gaps() -> None:
    near_ties = [
        _place(f"tie_{i}", f"Tied Cafe {i}", rating=4.5, reviews=400)
        for i in range(4)
    ]
    clearly_worse = _place("worse", "Weak Cafe", rating=3.6, reviews=45)
    ranked = near_ties + [clearly_worse]

    shuffled_a = _variety_shuffle(list(ranked), CostEstimate.mid, None, None, random.Random(7))
    shuffled_b = _variety_shuffle(list(ranked), CostEstimate.mid, None, None, random.Random(7))
    shuffled_c = _variety_shuffle(list(ranked), CostEstimate.mid, None, None, random.Random(8))

    # Deterministic for a given seed; a different seed may reorder the ties.
    assert shuffled_a == shuffled_b
    # The clearly-worse candidate can never be promoted into the tie group.
    assert shuffled_a[-1] == clearly_worse
    assert shuffled_c[-1] == clearly_worse
    # Only the near-tied head is permuted.
    assert set(p.provider_id for p in shuffled_a[:4]) == {f"tie_{i}" for i in range(4)}


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
                RawPlace(
                    "closed_rest", "Closed Fancy Room", "Road", 0.001, 0.0, 5.0, ["restaurant"], 1200,
                    price_range_start_inr=400, price_range_end_inr=800,
                ),
                RawPlace(
                    "open_rest", "Open Date Bistro", "Road", 0.002, 0.0, 4.5, ["restaurant"], 600,
                    price_range_start_inr=400, price_range_end_inr=800,
                ),
            ],
            "bakery": [
                RawPlace(
                    "bakery", "Late Bakery", "Road", 0.003, 0.0, 4.4, ["bakery"], 600,
                    price_range_start_inr=100, price_range_end_inr=200,
                ),
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


class UnknownHoursProvider:
    """Restaurant: top-ranked has unknown hours, weaker one is verifiably open.
    Bakery: the only candidate has unknown hours. Park: verifiably open."""

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
                RawPlace("no_hours_rest", "Mystery Hours Bistro", "Road", 0.001, 0.0, 4.9, ["restaurant"], 2000),
                RawPlace("open_rest", "Verified Open Bistro", "Road", 0.002, 0.0, 4.4, ["restaurant"], 300),
            ],
            "bakery": [
                RawPlace("no_hours_bakery", "Mystery Hours Bakery", "Road", 0.003, 0.0, 4.5, ["bakery"], 400),
            ],
            "park": [
                RawPlace("park", "Open Garden", "Road", 0.004, 0.0, 4.4, ["park"], 700),
            ],
        }
        return by_type.get(place_type, [])

    async def place_hours(self, *, provider_id: str, weekday: int) -> PlaceHours:
        hours = {
            "open_rest": PlaceHours("18:00", "23:00", False),
            "park": PlaceHours("06:00", "23:30", False),
        }
        return hours.get(provider_id, PlaceHours(None, None, False))


def test_unknown_hours_place_is_last_resort_not_hard_reject(monkeypatch) -> None:
    async def fake_narrative(**kwargs) -> str:
        return "A test quest."

    monkeypatch.setattr("quest_generator.generate_quest_narrative", fake_narrative)
    service = NearbyPlacesService(UnknownHoursProvider())
    req = QuestGenerationRequest(
        location="Govindpuram",
        occasion=Occasion.date,
        cost_estimate=CostEstimate.mid,
        people=2,
        duration_hours=3.0,
    )

    quest = asyncio.run(assemble_quest(req, service))

    names = [stop.place.name for stop in quest.stops]
    # A verifiably-open place beats a higher-ranked unknown-hours one...
    assert "Verified Open Bistro" in names
    assert "Mystery Hours Bistro" not in names
    # ...but when unknown hours is all there is, the stop is kept, not dropped.
    assert "Mystery Hours Bakery" in names


class StopCountProvider:
    """One good, always-open place per category the date template can ask for."""

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
            "restaurant": [RawPlace("rest", "Dinner Spot", "Road", 0.001, 0.0, 4.5, ["restaurant"], 600)],
            "bakery": [RawPlace("bakery", "Dessert Spot", "Road", 0.002, 0.0, 4.4, ["bakery"], 400)],
            "cafe": [RawPlace("cafe", "Coffee Spot", "Road", 0.003, 0.0, 4.6, ["cafe"], 500)],
            "tourist_attraction": [RawPlace("sight", "City Sight", "Road", 0.004, 0.0, 4.5, ["tourist_attraction"], 900)],
        }
        return by_type.get(place_type, [])

    async def place_hours(self, *, provider_id: str, weekday: int) -> PlaceHours:
        return PlaceHours(None, None, True)


def test_stop_count_selector_trims_and_extends_template(monkeypatch) -> None:
    async def fake_narrative(**kwargs) -> str:
        return "A test quest."

    monkeypatch.setattr("quest_generator.generate_quest_narrative", fake_narrative)

    def _quest(stop_count: int | None):
        service = NearbyPlacesService(StopCountProvider())
        return asyncio.run(assemble_quest(
            QuestGenerationRequest(
                location="Govindpuram",
                occasion=Occasion.date,
                cost_estimate=CostEstimate.mid,
                people=2,
                duration_hours=3.0,
                stop_count=stop_count,
            ),
            service,
        ))

    assert len(_quest(2).stops) == 2
    assert len(_quest(None).stops) == 3
    assert len(_quest(4).stops) == 4
    # 2 stops keeps the occasion's core pair (dinner + dessert for a date).
    assert [s.place.name for s in _quest(2).stops] == ["Dinner Spot", "Dessert Spot"]


def test_assemble_quest_surfaces_inr_estimates_and_totals(monkeypatch) -> None:
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

    bistro, bakery, park = quest.stops
    assert bistro.est_cost_per_person_min_inr == 400
    assert bistro.est_cost_per_person_max_inr == 800
    assert bistro.price_source == "google_price_range"
    assert bakery.est_cost_per_person_min_inr == 100
    # The park has no price signal and must not fabricate one.
    assert park.est_cost_per_person_min_inr is None
    assert park.price_source is None
    # Quest totals sum only the priced stops.
    assert quest.est_total_per_person_min_inr == 500
    assert quest.est_total_per_person_max_inr == 1000
