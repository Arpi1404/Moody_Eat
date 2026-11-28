"""Google's marketing tails come off a place's name where a search result
becomes a place, so every screen shows the same, shorter name."""

import asyncio

import pytest

from services.nearby_places_service import NearbyPlacesService
from models import NearbyPlacesRequest
from services.place_utils import tidy_place_name
from services.places_provider import RawPlace, ResolvedLocation


@pytest.mark.parametrize("raw, shown", [
    # From the recorded Google responses.
    ("Chulha Chauki Da Dhaba | Indiranagar", "Chulha Chauki Da Dhaba"),
    ("Amintiri - Cafe | Patisserie | Gifting", "Amintiri - Cafe"),
    ("Breakout® Escape Rooms | Koramangala | #1 Escape Room in Bangalore", "Breakout® Escape Rooms"),
    ("PHURR | Indiranagar", "PHURR"),
    ("Lush Cafe | By the lake", "Lush Cafe"),
    ("Zoroy Luxury Chocolate - Boutique Cafe HSR | Cake | Desserts",
     "Zoroy Luxury Chocolate - Boutique Cafe HSR"),
    # From the brief.
    ("Tossin Pizza | Sector 66, Gurgaon", "Tossin Pizza"),
    # " - " and brackets are part of many names: left alone.
    ("Jimmy - The Ginger", "Jimmy - The Ginger"),
    ("Public Park - Gafoor Nagar", "Public Park - Gafoor Nagar"),
    ("1 Bar House Kitchen (1BHK)", "1 Bar House Kitchen (1BHK)"),
    # Only a pipe with a space each side.
    ("Bar|Kitchen", "Bar|Kitchen"),
    # Too short once cut: the original stays.
    ("XO | Rooftop Bar", "XO | Rooftop Bar"),
    ("  Toit  ", "Toit"),
])
def test_a_name_loses_its_tail(raw: str, shown: str) -> None:
    assert tidy_place_name(raw) == shown


def _raw(pid: str, name: str) -> RawPlace:
    return RawPlace(pid, name, "Road", 0.001, 0.0, 4.5, ["restaurant"], 900,
                    primary_type="restaurant")


class Provider:
    async def geocode(self, query: str) -> ResolvedLocation:
        return ResolvedLocation(name=query, lat=0.0, lng=0.0)

    async def nearby_by_type(self, **kwargs):
        return [_raw("chulha", "Chulha Chauki Da Dhaba | Indiranagar")]

    async def search_by_text(self, **kwargs):
        return [_raw("chulha", "Chulha Chauki Da Dhaba | Indiranagar")]


def test_every_search_gives_the_tidy_name_and_keeps_the_id() -> None:
    service = NearbyPlacesService(Provider())
    by_type = asyncio.run(service.search(NearbyPlacesRequest(
        query="Somewhere", categories=["restaurant"], radius_meters=3000, limit=20,
    )))
    by_name = asyncio.run(service.search_by_name(text="chulha", lat=0.0, lng=0.0))
    by_intent = asyncio.run(service.search_by_intent(
        location="Somewhere", text="dinner", place_type="restaurant", max_distance_m=3000,
    ))
    for result in (by_type.places, by_name.places, by_intent):
        assert result[0].name == "Chulha Chauki Da Dhaba"
        assert result[0].provider_id == "chulha"


def test_the_quality_filter_still_reads_the_full_name() -> None:
    """A tail can carry what marks a place as not an outing (a phone number
    here): the filter runs before the name is tidied."""
    class WithPhone(Provider):
        async def nearby_by_type(self, **kwargs):
            return [_raw("x", "Good Food | Call 9876543210")]

    found = asyncio.run(NearbyPlacesService(WithPhone()).search(NearbyPlacesRequest(
        query="Somewhere", categories=["restaurant"], radius_meters=3000, limit=20,
    )))
    assert found.places == []
