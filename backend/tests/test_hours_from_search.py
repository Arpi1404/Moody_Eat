"""Opening hours, phone and website come with the search (Places API (New)).

A quest used to pay one Place Details call for every candidate it tried, just
to read its hours. The search now asks for them, so those calls go; one
fallback stays for places whose search did not ask (the legacy API).
"""

import asyncio
import json

import pytest

from models import (
    CostEstimate,
    DayPart,
    Occasion,
    PlaceItem,
    Quest,
    QuestGenerationRequest,
)
from quest_generator import _VIABILITY_CHECK_LIMIT, assemble_quest
from services.google_places import GooglePlacesProvider
from services.nearby_places_service import NearbyPlacesService
from services.places_provider import PlaceHours, RawPlace, ResolvedLocation, hours_for_weekday

LAT, LNG = 12.97, 77.64

# Every day, 08:00-23:00, in the shape Places API (New) answers with.
EVERY_DAY_8_TO_23 = [
    {"open": {"day": d, "hour": 8, "minute": 0}, "close": {"day": d, "hour": 23, "minute": 0}}
    for d in range(7)
]
# Every day, 06:00-09:00: shut for any evening visit.
EVERY_DAY_6_TO_9 = [
    {"open": {"day": d, "hour": 6, "minute": 0}, "close": {"day": d, "hour": 9, "minute": 0}}
    for d in range(7)
]


def _legacy(periods: list[dict]) -> tuple[dict, ...]:
    from services.google_places import _new_periods_to_legacy

    return tuple(_new_periods_to_legacy(periods))


def _settings():
    from config import Settings

    return Settings(google_places_api_key="test-key", use_new_places_api=True)


# ── The provider ──────────────────────────────────────────────────────────────


def test_a_search_result_carries_hours_phone_website_and_utc_offset() -> None:
    raw = GooglePlacesProvider._raw_from_new_place(
        {
            "id": "ChIJ1",
            "displayName": {"text": "Toit"},
            "location": {"latitude": LAT, "longitude": LNG},
            "regularOpeningHours": {"periods": EVERY_DAY_8_TO_23},
            "utcOffsetMinutes": 330,
            "internationalPhoneNumber": "+91 80 4123 4567",
            "websiteUri": "https://toit.example/",
        }
    )
    assert raw.opening_periods == _legacy(EVERY_DAY_8_TO_23)
    assert hours_for_weekday(raw.opening_periods, 5).opens_today == "08:00"
    assert raw.utc_offset_minutes == 330
    assert raw.phone == "+91 80 4123 4567"
    assert raw.website == "https://toit.example/"


def test_a_result_without_hours_is_known_to_list_none_and_needs_no_lookup() -> None:
    raw = GooglePlacesProvider._raw_from_new_place(
        {"id": "ChIJ2", "displayName": {"text": "Quiet Park"}, "location": {}}
    )
    # Asked for and absent: an empty week, not "not asked" (None).
    assert raw.opening_periods == ()
    assert raw.phone is None
    assert raw.website is None
    assert raw.utc_offset_minutes is None


def test_a_website_that_is_not_a_web_address_is_dropped() -> None:
    raw = GooglePlacesProvider._raw_from_new_place(
        {"id": "ChIJ3", "displayName": {"text": "X"}, "websiteUri": "javascript:alert(1)"}
    )
    assert raw.website is None


def test_a_legacy_search_result_does_not_claim_to_know_hours() -> None:
    raw = GooglePlacesProvider._raw_from_nearby_item(
        {"place_id": "p", "name": "Old API Cafe", "geometry": {"location": {"lat": 1, "lng": 2}}}
    )
    assert raw.opening_periods is None


# ── PlaceItem: stored and shared quests ──────────────────────────────────────

_PLACE = dict(name="A", address="B", lat=1.0, lng=2.0, distance_meters=3.0, provider_id="x")


def test_weekly_hours_stay_on_the_server() -> None:
    place = PlaceItem(**_PLACE, opening_periods=list(_legacy(EVERY_DAY_8_TO_23)), utc_offset_minutes=330)
    sent = json.loads(place.model_dump_json())
    assert "opening_periods" not in sent
    assert "utc_offset_minutes" not in sent
    assert "phone" in sent and "website" in sent


def test_a_quest_saved_before_this_change_still_reads() -> None:
    old = {
        "title": "An Evening Date",
        "occasion": "date",
        "total_duration_minutes": 60,
        "total_cost_estimate": "mid",
        "narrative": "An evening out.",
        "stops": [
            {
                "place": {**_PLACE, "opens_today": "08:00", "closes_today": "23:00"},
                "category": "restaurant",
                "time_block_start": "19:00",
                "time_block_end": "20:00",
                "why_this_place": "Good.",
            }
        ],
    }
    quest = Quest.model_validate(old)
    place = quest.stops[0].place
    assert place.phone is None and place.website is None and place.opening_periods is None


@pytest.mark.parametrize(
    "phone, kept",
    [
        ("+91 80 4123 4567", True),
        ("080-4123 4567", True),
        ("(022) 2202 3456", True),
        ("javascript:alert(1)", False),
        ("12", False),
        ("call us", False),
    ],
)
def test_only_a_plain_phone_number_is_kept(phone: str, kept: bool) -> None:
    assert (PlaceItem(**_PLACE, phone=phone).phone is not None) is kept


@pytest.mark.parametrize(
    "website, kept",
    [
        ("https://example.com/menu?x=1", True),
        ("http://example.com", True),
        ("javascript:alert(1)", False),
        ("data:text/html,hi", False),
        ("https://exa mple.com", False),
        ("example.com", False),
    ],
)
def test_only_a_web_address_is_kept(website: str, kept: bool) -> None:
    assert (PlaceItem(**_PLACE, website=website).website is not None) is kept


# ── The engine ───────────────────────────────────────────────────────────────


def _raw(pid: str, name: str, primary: str, periods: list[dict] | None, *, lat: float = 0.001,
         reviews: int = 600) -> RawPlace:
    return RawPlace(
        pid, name, "Road", lat, 0.0, 4.5, [primary], reviews,
        primary_type=primary,
        opening_periods=_legacy(periods) if periods is not None else None,
        phone="+91 80 4123 4567",
        website=f"https://{pid}.example/",
    )


class CountingProvider:
    """Places by searched type; counts every Place Details lookup."""

    def __init__(self, pools: dict[str, list[RawPlace]]) -> None:
        self.pools = pools
        self.hours_requested: list[str] = []

    async def geocode(self, query: str) -> ResolvedLocation:
        return ResolvedLocation(name=query, lat=0.0, lng=0.0)

    async def nearby_by_type(self, *, lat, lng, radius_meters, place_type, target_count=None):
        return list(self.pools.get(place_type, []))

    async def place_hours(self, *, provider_id: str, weekday: int) -> PlaceHours:
        self.hours_requested.append(provider_id)
        return PlaceHours(None, None, True)


@pytest.fixture(autouse=True)
def fake_narrative(monkeypatch):
    async def _narrative(**kwargs) -> str:
        return "A test quest."

    monkeypatch.setattr("quest_generator.generate_quest_narrative", _narrative)


def _date_dinner() -> QuestGenerationRequest:
    return QuestGenerationRequest(
        location="Somewhere",
        occasion=Occasion.date,
        cost_estimate=CostEstimate.mid,
        people=2,
        stop_count=1,
        day_part=DayPart.evening,
    )


def test_hours_from_the_search_cost_no_lookups_and_skip_a_shut_place() -> None:
    provider = CountingProvider({
        "restaurant": [
            # Ranked first (most reviews) but shut in the evening.
            _raw("breakfast", "Breakfast Club", "restaurant", EVERY_DAY_6_TO_9, reviews=9000),
            _raw("bistro", "Garden Bistro", "italian_restaurant", EVERY_DAY_8_TO_23),
        ],
    })
    quest = asyncio.run(assemble_quest(_date_dinner(), NearbyPlacesService(provider)))
    place = quest.stops[0].place
    assert place.name == "Garden Bistro"
    assert (place.opens_today, place.closes_today) == ("08:00", "23:00")
    assert place.phone == "+91 80 4123 4567"
    assert place.website == "https://bistro.example/"
    assert provider.hours_requested == []


def test_every_candidate_is_tried_when_trying_one_is_free() -> None:
    # More shut places than the paid-lookup limit, then one that is open.
    shut = [
        _raw(f"shut{i}", f"Morning Place {i}", "restaurant", EVERY_DAY_6_TO_9, reviews=9000 - i)
        for i in range(_VIABILITY_CHECK_LIMIT + 2)
    ]
    open_late = _raw("late", "Late Kitchen", "restaurant", EVERY_DAY_8_TO_23, reviews=500)
    provider = CountingProvider({"restaurant": shut + [open_late]})
    quest = asyncio.run(assemble_quest(_date_dinner(), NearbyPlacesService(provider)))
    assert quest.stops[0].place.name == "Late Kitchen"
    assert provider.hours_requested == []


def test_a_place_whose_search_did_not_ask_for_hours_falls_back_to_a_lookup() -> None:
    provider = CountingProvider({
        "restaurant": [_raw("legacy", "Old API Bistro", "restaurant", None)],
    })
    quest = asyncio.run(assemble_quest(_date_dinner(), NearbyPlacesService(provider)))
    assert quest.stops[0].place.name == "Old API Bistro"
    assert provider.hours_requested == ["legacy"]


def test_a_place_that_lists_no_hours_is_not_looked_up() -> None:
    provider = CountingProvider({
        "restaurant": [_raw("nohours", "No Hours Bistro", "restaurant", [])],
    })
    quest = asyncio.run(assemble_quest(_date_dinner(), NearbyPlacesService(provider)))
    # Still offered, as before, when nothing with known hours fits.
    assert quest.stops[0].place.name == "No Hours Bistro"
    assert quest.stops[0].place.opens_today is None
    assert provider.hours_requested == []


def test_search_by_name_brings_phone_and_website() -> None:
    class TextProvider(CountingProvider):
        async def search_by_text(self, *, text, lat, lng):
            return [_raw("toit", "Toit", "brewpub", EVERY_DAY_8_TO_23)]

    service = NearbyPlacesService(TextProvider({}), _settings())
    found = asyncio.run(service.search_by_name(text="toit", lat=0.0, lng=0.0))
    assert found.places[0].phone == "+91 80 4123 4567"
    assert found.places[0].website == "https://toit.example/"
