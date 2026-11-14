"""Search plumbing behind a quest: opening-hours windows, radius expansion,
geocode reuse, and device-location requests."""

import asyncio
from datetime import time

import pytest

from models import (
    ALLOWED_NEARBY_TYPES,
    CostEstimate,
    DayPart,
    NearbyPlacesRequest,
    Occasion,
    QuestGenerationRequest,
)
from quest_generator import (
    _LONG_QUEST_EXTRA_STOP,
    _search_with_expansion,
    _window_for_slot,
    assemble_quest,
)
from quest_templates import TEMPLATES
from services.google_places import _hours_for_weekday, _new_periods_to_legacy
from services.nearby_places_service import _TYPE_DENYLIST, NearbyPlacesService
from services.places_exceptions import LocationNotFoundError, PlacesProviderError
from services.places_provider import PlaceHours, RawPlace, ResolvedLocation


def _split_periods(*windows: tuple[tuple[int, int], tuple[int, int]]) -> list[dict]:
    """Places API (New) periods with the same windows on every weekday."""
    return [
        {
            "open": {"day": day, "hour": opens[0], "minute": opens[1]},
            "close": {"day": day, "hour": closes[0], "minute": closes[1]},
        }
        for day in range(7)
        for opens, closes in windows
    ]


# ── Opening hours: every window of the day counts ─────────────────────────────

LUNCH_AND_DINNER = _split_periods(((12, 0), (15, 30)), ((19, 0), (23, 0)))


def test_hours_for_weekday_keeps_every_window_of_a_split_day() -> None:
    hours = _hours_for_weekday(_new_periods_to_legacy(LUNCH_AND_DINNER), 6)

    assert hours.windows == (("12:00", "15:30"), ("19:00", "23:00"))
    # The summary pair still describes the first window of the day.
    assert (hours.opens_today, hours.closes_today) == ("12:00", "15:30")
    assert hours.open_24h_today is False


def test_hours_for_weekday_orders_windows_by_opening_time() -> None:
    periods = _split_periods(((16, 0), (18, 30)), ((5, 0), (9, 30)))

    hours = _hours_for_weekday(_new_periods_to_legacy(periods), 2)

    assert hours.windows == (("05:00", "09:30"), ("16:00", "18:30"))
    assert hours.opens_today == "05:00"


def test_hours_for_weekday_single_window_and_24h_are_unchanged() -> None:
    single = _hours_for_weekday(
        _new_periods_to_legacy(_split_periods(((11, 0), (23, 30)))), 3
    )
    always_open = _hours_for_weekday(
        _new_periods_to_legacy([{"open": {"day": 0, "hour": 0, "minute": 0}}]), 3
    )

    assert single == PlaceHours("11:00", "23:30", False, (("11:00", "23:30"),))
    assert always_open == PlaceHours(None, None, True)


def test_window_for_slot_picks_the_window_the_visit_falls_in() -> None:
    hours = _hours_for_weekday(_new_periods_to_legacy(LUNCH_AND_DINNER), 6)

    assert _window_for_slot(hours, time(13, 0), time(14, 0)) == ("12:00", "15:30")
    assert _window_for_slot(hours, time(20, 0), time(21, 0)) == ("19:00", "23:00")
    # In the afternoon gap nothing fits: the first window comes back and the
    # slot is rejected as closed by the usual rule.
    assert _window_for_slot(hours, time(16, 0), time(17, 0)) == ("12:00", "15:30")


def test_window_for_slot_falls_back_to_the_summary_pair_without_windows() -> None:
    legacy = PlaceHours("09:00", "22:00", False)

    assert _window_for_slot(legacy, time(20, 0), time(21, 0)) == ("09:00", "22:00")


class SplitShiftProvider:
    """One restaurant that closes between lunch and dinner, as Google reports it."""

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
        if place_type != "restaurant":
            return []
        return [
            RawPlace(
                "split", "Lunch And Dinner House", "Road", 0.001, 0.0, 4.5,
                ["restaurant"], 900,
            ),
        ]

    async def place_hours(self, *, provider_id: str, weekday: int) -> PlaceHours:
        return _hours_for_weekday(_new_periods_to_legacy(LUNCH_AND_DINNER), weekday)


def _one_stop_date(day_part: DayPart, **extra) -> QuestGenerationRequest:
    return QuestGenerationRequest(
        location=extra.pop("location", "Govindpuram"),
        occasion=Occasion.date,
        cost_estimate=CostEstimate.mid,
        people=2,
        stop_count=1,
        day_part=day_part,
        **extra,
    )


@pytest.fixture
def fake_narrative(monkeypatch) -> list[dict]:
    calls: list[dict] = []

    async def _narrative(**kwargs) -> str:
        calls.append(kwargs)
        return "A test quest."

    monkeypatch.setattr("quest_generator.generate_quest_narrative", _narrative)
    return calls


def test_dinner_slot_uses_the_evening_window_of_a_split_shift_place(fake_narrative) -> None:
    service = NearbyPlacesService(SplitShiftProvider())

    quest = asyncio.run(assemble_quest(_one_stop_date(DayPart.night), service))

    [stop] = quest.stops
    assert stop.place.name == "Lunch And Dinner House"
    # The stop card shows the hours that apply to the visit, not lunch service.
    assert (stop.place.opens_today, stop.place.closes_today) == ("19:00", "23:00")


def test_lunch_slot_uses_the_first_window_of_a_split_shift_place(fake_narrative) -> None:
    service = NearbyPlacesService(SplitShiftProvider())

    quest = asyncio.run(assemble_quest(_one_stop_date(DayPart.afternoon), service))

    [stop] = quest.stops
    assert (stop.place.opens_today, stop.place.closes_today) == ("12:00", "15:30")


def test_slot_in_the_midday_break_is_still_rejected(fake_narrative) -> None:
    service = NearbyPlacesService(SplitShiftProvider())

    # An evening quest starts 17:30 — after lunch service ends (15:30) and
    # before dinner begins (19:00) — so the only candidate is genuinely shut.
    with pytest.raises(ValueError):
        asyncio.run(assemble_quest(_one_stop_date(DayPart.evening), service))


# ── Templates never ask for a type the quality filter throws away ─────────────

def test_no_template_searches_a_deny_listed_type() -> None:
    stops = [stop for template in TEMPLATES.values() for stop in template]
    stops += list(_LONG_QUEST_EXTRA_STOP.values())
    searched = {place_type for stop in stops for place_type in stop.places_types}

    assert searched <= ALLOWED_NEARBY_TYPES
    # A deny-listed type returns nothing by construction — pure wasted calls.
    assert not searched & _TYPE_DENYLIST


# ── Radius expansion: sparse destination types probe the widest tier first ────

class RadiusRecordingProvider:
    def __init__(
        self,
        *,
        strong_from_radius: dict[str, int] | None = None,
        fail_radius: int | None = None,
    ) -> None:
        # place_type -> smallest radius at which three strong places appear.
        self.strong_from_radius = strong_from_radius or {}
        self.fail_radius = fail_radius
        self.searches: list[tuple[str, int]] = []
        self.geocodes: list[str] = []

    async def geocode(self, query: str) -> ResolvedLocation:
        self.geocodes.append(query)
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
        self.searches.append((place_type, radius_meters))
        if radius_meters == self.fail_radius:
            raise PlacesProviderError("boom")
        threshold = self.strong_from_radius.get(place_type)
        if threshold is None or radius_meters < threshold:
            return []
        return [
            RawPlace(f"{place_type}{i}", f"Big {place_type} {i}", "Road", 0.01 * i, 0.0, 4.6, [place_type], 800)
            for i in range(1, 4)
        ]

    async def place_hours(self, *, provider_id: str, weekday: int) -> PlaceHours:
        return PlaceHours("08:00", "23:00", False)


def test_sparse_type_with_nothing_in_reach_costs_one_search() -> None:
    provider = RadiusRecordingProvider()
    service = NearbyPlacesService(provider)

    found = asyncio.run(_search_with_expansion(service, "Kukatpally", "zoo"))

    assert found == []
    assert provider.searches == [("zoo", 10_000)]


def test_sparse_type_that_exists_expands_as_usual_and_reuses_the_wide_result() -> None:
    provider = RadiusRecordingProvider(strong_from_radius={"zoo": 6_000})
    service = NearbyPlacesService(provider)

    found = asyncio.run(_search_with_expansion(service, "Bahadurpura", "zoo"))

    assert [p.provider_id for p in found] == ["zoo1", "zoo2", "zoo3"]
    # Wide probe first, then near-to-far; the hit at 6 km ends the expansion.
    assert provider.searches == [("zoo", 10_000), ("zoo", 3_000), ("zoo", 6_000)]


def test_sparse_type_found_only_at_the_widest_tier_is_not_searched_twice() -> None:
    provider = RadiusRecordingProvider(strong_from_radius={"aquarium": 10_000})
    service = NearbyPlacesService(provider)

    found = asyncio.run(_search_with_expansion(service, "Somewhere", "aquarium"))

    assert len(found) == 3
    assert provider.searches == [
        ("aquarium", 10_000),
        ("aquarium", 3_000),
        ("aquarium", 6_000),
    ]


def test_failed_wide_probe_does_not_blank_a_sparse_type() -> None:
    provider = RadiusRecordingProvider(
        strong_from_radius={"zoo": 3_000},
        fail_radius=10_000,
    )
    service = NearbyPlacesService(provider)

    found = asyncio.run(_search_with_expansion(service, "Bahadurpura", "zoo"))

    assert len(found) == 3
    assert provider.searches[:2] == [("zoo", 10_000), ("zoo", 3_000)]


def test_common_types_still_expand_near_to_far() -> None:
    provider = RadiusRecordingProvider()
    service = NearbyPlacesService(provider)

    found = asyncio.run(_search_with_expansion(service, "Somewhere", "park"))

    assert found == []
    assert provider.searches == [("park", 3_000), ("park", 6_000), ("park", 10_000)]


# ── Geocoding: one paid lookup per distinct query ─────────────────────────────

def test_repeat_searches_for_one_location_geocode_once() -> None:
    provider = RadiusRecordingProvider()
    service = NearbyPlacesService(provider)

    async def _run() -> None:
        await service.resolve_location("Banjara Hills")
        for place_type, radius in (("cafe", 3_000), ("bar", 3_000), ("cafe", 6_000)):
            await service.search(NearbyPlacesRequest(
                query="Banjara Hills",
                categories=[place_type],
                radius_meters=radius,
            ))

    asyncio.run(_run())

    assert provider.geocodes == ["Banjara Hills"]
    assert len(provider.searches) == 3


def test_failed_geocode_is_not_remembered() -> None:
    class FlakyGeocoder(RadiusRecordingProvider):
        async def geocode(self, query: str) -> ResolvedLocation:
            self.geocodes.append(query)
            if len(self.geocodes) == 1:
                raise LocationNotFoundError("nowhere", provider_status="ZERO_RESULTS")
            return ResolvedLocation(name=query, lat=1.0, lng=2.0)

    provider = FlakyGeocoder()
    service = NearbyPlacesService(provider)

    async def _run() -> ResolvedLocation:
        with pytest.raises(LocationNotFoundError):
            await service.resolve_location("Somewhere")
        return await service.resolve_location("Somewhere")

    resolved = asyncio.run(_run())

    assert (resolved.lat, resolved.lng) == (1.0, 2.0)
    assert provider.geocodes == ["Somewhere", "Somewhere"]


# ── Device location: coordinates anchor the search, the label names the quest ─

def test_coordinate_location_with_label_names_the_quest_after_the_area(fake_narrative) -> None:
    provider = SplitShiftProvider()
    service = NearbyPlacesService(provider)
    req = _one_stop_date(
        DayPart.night,
        location="17.440,78.349",
        location_label="Gachibowli, Hyderabad",
    )

    quest = asyncio.run(assemble_quest(req, service))

    assert quest.title == "An Evening Date in Gachibowli"
    # The narrative model is told the area in words, never the coordinates.
    assert fake_narrative[0]["location"] == "Gachibowli, Hyderabad"


def test_coordinate_location_without_label_never_shows_the_numbers(fake_narrative) -> None:
    service = NearbyPlacesService(SplitShiftProvider())
    req = _one_stop_date(DayPart.night, location="17.440,78.349")

    quest = asyncio.run(assemble_quest(req, service))

    assert quest.title == "An Evening Date"
    assert fake_narrative[0]["location"] == "your area"


def test_typed_location_is_unaffected_by_the_label_field(fake_narrative) -> None:
    service = NearbyPlacesService(SplitShiftProvider())

    quest = asyncio.run(assemble_quest(_one_stop_date(DayPart.night), service))

    assert quest.title == "An Evening Date in Govindpuram"
    assert fake_narrative[0]["location"] == "Govindpuram"


def test_search_is_anchored_to_the_coordinates_not_the_label(fake_narrative) -> None:
    provider = RadiusRecordingProvider(strong_from_radius={"restaurant": 3_000})
    service = NearbyPlacesService(provider)
    req = _one_stop_date(
        DayPart.night,
        location="17.440,78.349",
        location_label="Gachibowli, Hyderabad",
    )

    asyncio.run(assemble_quest(req, service))

    assert set(provider.geocodes) == {"17.440,78.349"}
