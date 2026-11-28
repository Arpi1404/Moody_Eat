"""A date's meal is found by a Text Search phrased by intent, not by size.

The search replaces the `restaurant` type search; when it finds too few usable
places the stop searches by type as before.
"""

import asyncio

import pytest

from models import CostEstimate, DayPart, Occasion, QuestGenerationRequest
from quest_generator import (
    _INTENT_MAX_DISTANCE_M,
    _INTENT_QUERIES,
    assemble_quest,
)
from services.nearby_places_service import NearbyPlacesService
from services.places_provider import PlaceHours, RawPlace, ResolvedLocation

# ~111 m per 0.001 degree of latitude at the equator.
NEAR = 0.002
FAR = (_INTENT_MAX_DISTANCE_M + 1_000) / 111_000


def _raw(pid: str, name: str, primary: str, *, lat: float = NEAR, reviews: int = 900,
         rating: float = 4.5, price_level: int | None = 2) -> RawPlace:
    return RawPlace(pid, name, "Road", lat, 0.0, rating, [primary, "restaurant"], reviews,
                    price_level=price_level, primary_type=primary)


# The busiest places in the area: what a type search ranks first.
CHAINS = [
    _raw("chain1", "Biryani Chain", "south_indian_restaurant", reviews=22_000),
    _raw("chain2", "Tiffin Room", "vegetarian_restaurant", reviews=18_000, price_level=1),
    _raw("chain3", "Dhaba Chain", "north_indian_restaurant", reviews=6_400),
]
# What a search for a date dinner returns, best match first.
DATE_PLACES = [
    _raw("bistro", "Candle Bistro", "italian_restaurant", reviews=1_100),
    _raw("terrace", "Rooftop Terrace", "european_restaurant", reviews=700),
    _raw("garden", "Garden Table", "mediterranean_restaurant", reviews=2_800),
    _raw("tasting", "Tasting Room", "fine_dining_restaurant", reviews=500, price_level=4),
]


class IntentProvider:
    def __init__(self, text_results: list[RawPlace]) -> None:
        self.text_results = text_results
        self.texts: list[dict] = []
        self.nearby: list[str] = []

    async def geocode(self, query: str) -> ResolvedLocation:
        return ResolvedLocation(name=query, lat=0.0, lng=0.0)

    async def nearby_by_type(self, *, lat, lng, radius_meters, place_type, target_count=None):
        self.nearby.append(place_type)
        if place_type == "restaurant":
            return list(CHAINS)
        if place_type == "bakery":
            return [RawPlace("cake", "Cake Cafe", "Road", NEAR, 0.0, 4.5, ["bakery", "cafe"], 800,
                             primary_type="bakery")]
        return []

    async def search_by_text(self, *, text, lat, lng, included_type=None, bias_radius_m=None):
        self.texts.append({"text": text, "type": included_type, "bias": bias_radius_m})
        return list(self.text_results)

    async def place_hours(self, *, provider_id: str, weekday: int) -> PlaceHours:
        return PlaceHours(None, None, True)


@pytest.fixture(autouse=True)
def fake_narrative(monkeypatch):
    async def _narrative(**kwargs) -> str:
        return "A test quest."

    monkeypatch.setattr("quest_generator.generate_quest_narrative", _narrative)


def _quest(provider, occasion=Occasion.date, cost=CostEstimate.mid, stops=1,
           day_part=DayPart.evening, **extra):
    req = QuestGenerationRequest(location="Somewhere", occasion=occasion, cost_estimate=cost,
                                 people=2, stop_count=stops, day_part=day_part, **extra)
    return asyncio.run(assemble_quest(req, NearbyPlacesService(provider)))


def test_a_date_dinner_comes_from_the_intent_search_instead_of_the_type_search() -> None:
    provider = IntentProvider(DATE_PLACES)
    quest = _quest(provider)

    assert quest.stops[0].place.name in {p.name for p in DATE_PLACES}
    assert provider.texts == [{
        "text": _INTENT_QUERIES[(Occasion.date, "dinner")][CostEstimate.mid],
        "type": "restaurant",
        "bias": _INTENT_MAX_DISTANCE_M,
    }]
    # Replaced, not added: no restaurant type search at all.
    assert "restaurant" not in provider.nearby


def test_a_date_quest_makes_one_text_search_at_most() -> None:
    provider = IntentProvider(DATE_PLACES)
    _quest(provider, stops=4)
    assert len(provider.texts) == 1


def test_too_few_usable_places_fall_back_to_the_type_search() -> None:
    # Two places is below the bar; the third is too far away to count.
    far = _raw("far", "Faraway Fine Dining", "fine_dining_restaurant", lat=FAR)
    provider = IntentProvider(DATE_PLACES[:2] + [far])
    quest = _quest(provider)

    assert provider.nearby[0] == "restaurant"
    assert quest.stops[0].place.name in {p.name for p in CHAINS}


def test_a_place_outside_the_area_is_never_picked() -> None:
    far = _raw("far", "Faraway Fine Dining", "fine_dining_restaurant", lat=FAR, reviews=9_000)
    provider = IntentProvider([far] + DATE_PLACES)
    for seed in range(8):
        quest = _quest(provider, variety_seed=seed)
        assert quest.stops[0].place.name != "Faraway Fine Dining"


def test_a_cheap_date_does_not_get_an_expensive_dinner() -> None:
    pricey = [
        _raw(f"p{i}", f"Pricey {i}", "fine_dining_restaurant", price_level=4) for i in range(3)
    ]
    cheap_ok = _raw("ok", "Corner Bistro", "italian_restaurant", price_level=1, reviews=300)
    provider = IntentProvider(pricey + [cheap_ok])
    quest = _quest(provider, cost=CostEstimate.cheap)

    assert provider.texts[0]["text"] == _INTENT_QUERIES[(Occasion.date, "dinner")][CostEstimate.cheap]
    assert quest.stops[0].place.name == "Corner Bistro"


def test_shuffle_still_varies_the_dinner() -> None:
    provider = IntentProvider(DATE_PLACES)
    picks = {_quest(provider, variety_seed=seed).stops[0].place.name for seed in range(12)}
    assert len(picks) >= 2


def test_recently_seen_places_are_still_avoided() -> None:
    provider = IntentProvider(DATE_PLACES)
    first = _quest(provider).stops[0].place
    again = _quest(provider, exclude_place_ids=[first.provider_id]).stops[0].place
    assert again.provider_id != first.provider_id


def test_a_lunch_date_uses_the_lunch_phrase() -> None:
    provider = IntentProvider(DATE_PLACES)
    _quest(provider, day_part=DayPart.afternoon)
    assert provider.texts[0]["text"] == _INTENT_QUERIES[(Occasion.date, "lunch")][CostEstimate.mid]


@pytest.mark.parametrize("occasion", [Occasion.friends, Occasion.solo, Occasion.family])
def test_other_occasions_still_search_by_type(occasion) -> None:
    provider = IntentProvider(DATE_PLACES)
    _quest(provider, occasion=occasion, stops=2, day_part=DayPart.night)
    assert provider.texts == []
    assert "restaurant" in provider.nearby


def test_a_failed_intent_search_falls_back_quietly() -> None:
    from services.places_exceptions import ProviderTimeoutError

    class Failing(IntentProvider):
        async def search_by_text(self, **kwargs):
            raise ProviderTimeoutError("slow")

    provider = Failing(DATE_PLACES)
    quest = _quest(provider)
    assert quest.stops[0].place.name in {p.name for p in CHAINS}
