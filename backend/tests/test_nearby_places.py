import logging

import pytest
from fastapi.testclient import TestClient

from config import get_settings
from deps import get_nearby_places_service
from main import app
from services.nearby_places_service import NearbyPlacesService
from services.places_exceptions import LocationNotFoundError
from services.places_provider import PlacesProvider, RawPlace, ResolvedLocation


class FakeProvider(PlacesProvider):
    def __init__(
        self,
        *,
        empty_nearby: bool = False,
        duplicate_across_types: bool = False,
    ) -> None:
        self.empty_nearby = empty_nearby
        self.duplicate_across_types = duplicate_across_types
        self.geocode_queries: list[str] = []
        self.nearby_types: list[str] = []

    async def geocode(self, query: str) -> ResolvedLocation:
        self.geocode_queries.append(query)
        return ResolvedLocation(name="Test Point", lat=0.0, lng=0.0)

    async def nearby_by_type(
        self,
        *,
        lat: float,
        lng: float,
        radius_meters: int,
        place_type: str,
        target_count: int | None = None,
    ) -> list[RawPlace]:
        self.nearby_types.append(place_type)
        if self.empty_nearby:
            return []
        base = [
            RawPlace("p_far", "Far Cafe", "Road 1", 0.01, 0.0, 4.0, ["cafe"], 100, "OPERATIONAL"),
            RawPlace("p_near", "Near Cafe", "Road 2", 0.001, 0.0, 4.5, ["cafe"], 100, "OPERATIONAL"),
        ]
        if self.duplicate_across_types and place_type == "restaurant":
            return [
                RawPlace("p_near", "Near Cafe", "Road 2", 0.001, 0.0, 4.5, ["restaurant"], 100, "OPERATIONAL"),
            ]
        return base


class FailingGeocodeProvider(FakeProvider):
    async def geocode(self, query: str) -> ResolvedLocation:
        raise LocationNotFoundError("nowhere", provider_status="ZERO_RESULTS")


@pytest.fixture
def client() -> TestClient:
    settings = get_settings()
    svc = NearbyPlacesService(FakeProvider(), settings)
    app.dependency_overrides[get_nearby_places_service] = lambda: svc
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_nearby_returns_sorted_by_distance(client: TestClient) -> None:
    res = client.post(
        "/api/places/nearby",
        json={"query": "Somewhere", "categories": ["cafe"], "limit": 20},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["count"] == 2
    names = [p["name"] for p in body["places"]]
    assert names == ["Near Cafe", "Far Cafe"]
    assert body["places"][0]["distance_meters"] < body["places"][1]["distance_meters"]


def test_nearby_respects_limit(client: TestClient) -> None:
    res = client.post(
        "/api/places/nearby",
        json={"query": "Somewhere", "categories": ["cafe"], "limit": 1},
    )
    assert res.status_code == 200
    assert res.json()["count"] == 1


def test_nearby_surfaces_price_level() -> None:
    class PriceProvider(FakeProvider):
        async def nearby_by_type(
            self,
            *,
            lat: float,
            lng: float,
            radius_meters: int,
            place_type: str,
            target_count: int | None = None,
        ) -> list[RawPlace]:
            self.nearby_types.append(place_type)
            return [
                RawPlace(
                    "priced",
                    "Priced Cafe",
                    "Road",
                    0.001,
                    0.0,
                    4.5,
                    ["cafe"],
                    100,
                    "OPERATIONAL",
                    price_level=1,
                ),
            ]

    settings = get_settings()
    provider = PriceProvider()
    svc = NearbyPlacesService(provider, settings)
    app.dependency_overrides[get_nearby_places_service] = lambda: svc
    try:
        with TestClient(app) as c:
            res = c.post("/api/places/nearby", json={"query": "Somewhere", "categories": ["cafe"]})
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 200
    assert res.json()["places"][0]["price_level"] == 1


def test_nearby_zero_results(client: TestClient) -> None:
    settings = get_settings()
    svc = NearbyPlacesService(FakeProvider(empty_nearby=True), settings)
    app.dependency_overrides[get_nearby_places_service] = lambda: svc
    try:
        with TestClient(app) as c:
            res = c.post("/api/places/nearby", json={"query": "Empty", "categories": ["cafe"]})
    finally:
        app.dependency_overrides.clear()
    assert res.status_code == 200
    assert res.json()["count"] == 0


def test_nearby_dedupes_across_categories() -> None:
    settings = get_settings()
    svc = NearbyPlacesService(FakeProvider(duplicate_across_types=True), settings)
    app.dependency_overrides[get_nearby_places_service] = lambda: svc
    try:
        with TestClient(app) as c:
            res = c.post(
                "/api/places/nearby",
                json={"query": "Somewhere", "categories": ["cafe", "restaurant"], "limit": 20},
            )
    finally:
        app.dependency_overrides.clear()
    assert res.status_code == 200
    body = res.json()
    assert body["count"] == 2


def test_validation_limit_max_20() -> None:
    settings = get_settings()
    svc = NearbyPlacesService(FakeProvider(), settings)
    app.dependency_overrides[get_nearby_places_service] = lambda: svc
    try:
        with TestClient(app) as c:
            res = c.post("/api/places/nearby", json={"query": "x", "limit": 21})
    finally:
        app.dependency_overrides.clear()
    assert res.status_code == 422


def test_geocode_not_found_maps_to_404() -> None:
    settings = get_settings()
    svc = NearbyPlacesService(FailingGeocodeProvider(), settings)
    app.dependency_overrides[get_nearby_places_service] = lambda: svc
    try:
        with TestClient(app) as c:
            res = c.post("/api/places/nearby", json={"query": "bad"})
    finally:
        app.dependency_overrides.clear()
    assert res.status_code == 404
    assert "message" in res.json()["detail"]


def test_query_intent_cafe_narrows_default_categories() -> None:
    settings = get_settings()
    provider = FakeProvider()
    svc = NearbyPlacesService(provider, settings)
    app.dependency_overrides[get_nearby_places_service] = lambda: svc
    try:
        with TestClient(app) as c:
            res = c.post("/api/places/nearby", json={"query": "cafes near Bangalore"})
    finally:
        app.dependency_overrides.clear()
    assert res.status_code == 200
    # Default categories ["cafe", "restaurant"] should narrow to cafe intent.
    assert provider.nearby_types == ["cafe"]
    # The geocoder should resolve the location phrase, not "cafe".
    assert provider.geocode_queries == ["bangalore"]


def test_query_intent_prefers_matching_type_when_distances_equal() -> None:
    class IntentProvider(FakeProvider):
        async def nearby_by_type(
            self,
            *,
            lat: float,
            lng: float,
            radius_meters: int,
            place_type: str,
            target_count: int | None = None,
        ) -> list[RawPlace]:
            self.nearby_types.append(place_type)
            return [
                RawPlace("restaurant_1", "Dinner Point", "Road", 0.001, 0.0, 4.8, ["restaurant"], 100),
                RawPlace("cafe_1", "Brewed Awakenings", "Road", 0.001, 0.0, 4.3, ["cafe"], 100),
            ]

    settings = get_settings()
    provider = IntentProvider()
    svc = NearbyPlacesService(provider, settings)
    app.dependency_overrides[get_nearby_places_service] = lambda: svc
    try:
        with TestClient(app) as c:
            res = c.post(
                "/api/places/nearby",
                json={"query": "cafe in test city", "categories": ["cafe", "restaurant"]},
            )
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 200
    names = [p["name"] for p in res.json()["places"]]
    assert names[0] == "Brewed Awakenings"


def test_quality_filter_drops_unrated_noise_when_strict_pool_exists() -> None:
    class QualityProvider(FakeProvider):
        async def nearby_by_type(
            self,
            *,
            lat: float,
            lng: float,
            radius_meters: int,
            place_type: str,
            target_count: int | None = None,
        ) -> list[RawPlace]:
            self.nearby_types.append(place_type)
            return [
                RawPlace("n1", "Ravi", "CF4G+HVX, Hyderabad", 0.0, 0.0, None, ["bar"], 0, "OPERATIONAL"),
                RawPlace("g1", "Good Bar 1", "Addr1", 0.001, 0.0, 4.6, ["bar"], 250, "OPERATIONAL"),
                RawPlace("g2", "Good Bar 2", "Addr2", 0.0011, 0.0, 4.5, ["bar"], 200, "OPERATIONAL"),
                RawPlace("g3", "Good Bar 3", "Addr3", 0.0012, 0.0, 4.4, ["bar"], 180, "OPERATIONAL"),
                RawPlace("g4", "Good Bar 4", "Addr4", 0.0013, 0.0, 4.3, ["bar"], 150, "OPERATIONAL"),
                RawPlace("g5", "Good Bar 5", "Addr5", 0.0014, 0.0, 4.2, ["bar"], 120, "OPERATIONAL"),
            ]

    settings = get_settings()
    provider = QualityProvider()
    svc = NearbyPlacesService(provider, settings)
    app.dependency_overrides[get_nearby_places_service] = lambda: svc
    try:
        with TestClient(app) as c:
            res = c.post("/api/places/nearby", json={"query": "bar in Hyderabad", "categories": ["bar"]})
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 200
    names = [p["name"] for p in res.json()["places"]]
    assert "Ravi" not in names


def test_quality_filter_does_not_relax_when_strict_pool_is_small() -> None:
    class SmallStrictProvider(FakeProvider):
        async def nearby_by_type(
            self,
            *,
            lat: float,
            lng: float,
            radius_meters: int,
            place_type: str,
            target_count: int | None = None,
        ) -> list[RawPlace]:
            self.nearby_types.append(place_type)
            return [
                RawPlace("weak", "Thin Signal Cafe", "Road", 0.001, 0.0, 4.9, ["cafe"], 8),
                RawPlace("good", "Known Cafe", "Road", 0.002, 0.0, 4.0, ["cafe"], 40),
            ]

    settings = get_settings()
    provider = SmallStrictProvider()
    svc = NearbyPlacesService(provider, settings)
    app.dependency_overrides[get_nearby_places_service] = lambda: svc
    try:
        with TestClient(app) as c:
            res = c.post("/api/places/nearby", json={"query": "cafe in Hyderabad", "categories": ["cafe"]})
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 200
    names = [p["name"] for p in res.json()["places"]]
    assert names == ["Known Cafe"]


def test_quality_filter_drops_type_denylist_matches() -> None:
    class TypeDenylistProvider(FakeProvider):
        async def nearby_by_type(
            self,
            *,
            lat: float,
            lng: float,
            radius_meters: int,
            place_type: str,
            target_count: int | None = None,
        ) -> list[RawPlace]:
            self.nearby_types.append(place_type)
            return [
                RawPlace("travel", "Heritage Tours", "Road", 0.001, 0.0, 4.8, ["tourist_attraction", "travel_agency"], 1000),
                RawPlace("fort", "Real Fort", "Road", 0.002, 0.0, 4.6, ["tourist_attraction"], 1000),
            ]

    settings = get_settings()
    provider = TypeDenylistProvider()
    svc = NearbyPlacesService(provider, settings)
    app.dependency_overrides[get_nearby_places_service] = lambda: svc
    try:
        with TestClient(app) as c:
            res = c.post(
                "/api/places/nearby",
                json={"query": "attractions in Hyderabad", "categories": ["tourist_attraction"]},
            )
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 200
    names = [p["name"] for p in res.json()["places"]]
    assert names == ["Real Fort"]


def test_quality_filter_drops_plain_store_without_food_or_culture_type() -> None:
    class StoreProvider(FakeProvider):
        async def nearby_by_type(
            self,
            *,
            lat: float,
            lng: float,
            radius_meters: int,
            place_type: str,
            target_count: int | None = None,
        ) -> list[RawPlace]:
            self.nearby_types.append(place_type)
            return [
                RawPlace("store", "Generic Store", "Road", 0.001, 0.0, 4.8, ["store"], 500),
                RawPlace("cafe_store", "Cafe With Shelves", "Road", 0.002, 0.0, 4.4, ["cafe", "store"], 500),
            ]

    settings = get_settings()
    provider = StoreProvider()
    svc = NearbyPlacesService(provider, settings)
    app.dependency_overrides[get_nearby_places_service] = lambda: svc
    try:
        with TestClient(app) as c:
            res = c.post("/api/places/nearby", json={"query": "cafes in Hyderabad", "categories": ["cafe"]})
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 200
    names = [p["name"] for p in res.json()["places"]]
    assert names == ["Cafe With Shelves"]


def test_quality_filter_drops_name_denylist_matches() -> None:
    class NameDenylistProvider(FakeProvider):
        async def nearby_by_type(
            self,
            *,
            lat: float,
            lng: float,
            radius_meters: int,
            place_type: str,
            target_count: int | None = None,
        ) -> list[RawPlace]:
            self.nearby_types.append(place_type)
            return [
                RawPlace("noise", "Raj Consultancy Cafe", "Road", 0.001, 0.0, 4.8, ["cafe"], 500),
                RawPlace("good", "Garden Cafe", "Road", 0.002, 0.0, 4.4, ["cafe"], 500),
            ]

    settings = get_settings()
    provider = NameDenylistProvider()
    svc = NearbyPlacesService(provider, settings)
    app.dependency_overrides[get_nearby_places_service] = lambda: svc
    try:
        with TestClient(app) as c:
            res = c.post("/api/places/nearby", json={"query": "cafes in Hyderabad", "categories": ["cafe"]})
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 200
    names = [p["name"] for p in res.json()["places"]]
    assert names == ["Garden Cafe"]


def test_quality_filter_uses_higher_bar_for_noisy_requested_types() -> None:
    class NoisyTypeProvider(FakeProvider):
        async def nearby_by_type(
            self,
            *,
            lat: float,
            lng: float,
            radius_meters: int,
            place_type: str,
            target_count: int | None = None,
        ) -> list[RawPlace]:
            self.nearby_types.append(place_type)
            return [
                # Below the new 4.3/300 floor — drop.
                RawPlace("low_rating", "Chapter Two", "Road", 0.001, 0.0, 4.2, ["book_store"], 500),
                RawPlace("low_reviews", "Page Turner", "Road", 0.002, 0.0, 4.5, ["book_store"], 299),
                # Clean book_store (no `store` co-tag) clearing the floor — keep.
                RawPlace("good", "Crossword", "Road", 0.003, 0.0, 4.4, ["book_store"], 500),
            ]

    settings = get_settings()
    provider = NoisyTypeProvider()
    svc = NearbyPlacesService(provider, settings)
    app.dependency_overrides[get_nearby_places_service] = lambda: svc
    try:
        with TestClient(app) as c:
            res = c.post("/api/places/nearby", json={"query": "bookstores in Hyderabad", "categories": ["book_store"]})
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 200
    names = [p["name"] for p in res.json()["places"]]
    assert names == ["Crossword"]


def test_quality_filter_drops_stationery_disguised_as_bookstore() -> None:
    """`book_store` + `store` co-tag is the Indian stationery-shop tell.

    Drops the entire family of "Books Gallery / Book World / Book Centre / Book Mart"
    style places unless they have Crossword-tier consensus (≥4.4★ and ≥1000 reviews).
    """

    class StationeryDisguiseProvider(FakeProvider):
        async def nearby_by_type(
            self,
            *,
            lat: float,
            lng: float,
            radius_meters: int,
            place_type: str,
            target_count: int | None = None,
        ) -> list[RawPlace]:
            self.nearby_types.append(place_type)
            return [
                # Name pattern (Vidya Books Gallery / Book World / Book Centre):
                # dropped by the book_store name denylist regardless of stats.
                RawPlace("vidya", "Vidya Books Gallery", "Road", 0.001, 0.0, 4.8, ["book_store", "store"], 5000),
                RawPlace("book_world", "Book World", "Road", 0.002, 0.0, 4.3, ["book_store", "store"], 279),
                RawPlace("book_centre", "Book Centre", "Road", 0.003, 0.0, 4.5, ["book_store", "store"], 600),
                RawPlace("book_mart", "Book Mart", "Road", 0.004, 0.0, 4.6, ["book_store", "store"], 400),
                # No name pattern but `store` co-tag + sub-Crossword stats: dropped
                # by the book_store+store combo rule.
                RawPlace("ok_stats", "Reader's Den", "Road", 0.005, 0.0, 4.4, ["book_store", "store"], 800),
                # Crossword-tier: `store` co-tag but ≥4.4 AND ≥1000 reviews. Keep.
                RawPlace("crossword", "Crossword Bookstores", "Road", 0.006, 0.0, 4.4, ["book_store", "store"], 1500),
                # Clean type tagging, comfortably above the noisy floor. Keep.
                RawPlace("clean", "Chapter One", "Road", 0.007, 0.0, 4.5, ["book_store"], 700),
            ]

    settings = get_settings()
    provider = StationeryDisguiseProvider()
    svc = NearbyPlacesService(provider, settings)
    app.dependency_overrides[get_nearby_places_service] = lambda: svc
    try:
        with TestClient(app) as c:
            res = c.post("/api/places/nearby", json={"query": "bookstores in Hyderabad", "categories": ["book_store"]})
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 200
    names = sorted(p["name"] for p in res.json()["places"])
    assert names == ["Chapter One", "Crossword Bookstores"]


def test_quality_filter_logs_rule_counts_without_place_names(caplog: pytest.LogCaptureFixture) -> None:
    class LoggingProvider(FakeProvider):
        async def nearby_by_type(
            self,
            *,
            lat: float,
            lng: float,
            radius_meters: int,
            place_type: str,
            target_count: int | None = None,
        ) -> list[RawPlace]:
            self.nearby_types.append(place_type)
            return [
                RawPlace("noise", "Secret Agency Noise", "Road", 0.001, 0.0, 4.8, ["cafe", "travel_agency"], 500),
                RawPlace("good", "Quiet Cafe", "Road", 0.002, 0.0, 4.4, ["cafe"], 500),
            ]

    settings = get_settings()
    provider = LoggingProvider()
    svc = NearbyPlacesService(provider, settings)
    app.dependency_overrides[get_nearby_places_service] = lambda: svc
    try:
        with caplog.at_level(logging.INFO, logger="services.nearby_places_service"):
            with TestClient(app) as c:
                res = c.post("/api/places/nearby", json={"query": "cafes in Hyderabad", "categories": ["cafe"]})
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 200
    assert "type_denylist': 1" in caplog.text
    assert "Secret Agency Noise" not in caplog.text


def test_curated_quests_return_v1_quest_objects() -> None:
    with TestClient(app) as c:
        res = c.get("/api/quests/curated?city=Hyderabad")

    assert res.status_code == 200
    body = res.json()
    assert isinstance(body, list)
    assert len(body) > 0
    first = body[0]
    assert set(first) >= {
        "id",
        "title",
        "occasion",
        "stops",
        "total_duration_minutes",
        "total_cost_estimate",
        "narrative",
        "created_at",
    }
    assert len(first["stops"]) == 3
    assert "place" in first["stops"][0]
    assert "why_this_place" in first["stops"][0]


def _quest_payload() -> dict:
    return {
        "id": "11111111-1111-4111-8111-111111111111",
        "title": "Test Quest",
        "occasion": "date",
        "stops": [
            {
                "place": {
                    "name": "Previous Place",
                    "address": "Prev Road",
                    "lat": 0.0,
                    "lng": 0.0,
                    "distance_meters": 0,
                    "rating": 4.2,
                    "user_ratings_total": 100,
                    "types": ["cafe"],
                    "provider_id": "prev",
                },
                "category": "cafe",
                "time_block_start": "19:00",
                "time_block_end": "19:40",
                "travel_to_next_minutes": 1,
                "travel_mode": "walking",
                "why_this_place": "Previous pick.",
            },
            {
                "place": {
                    "name": "Original Dinner",
                    "address": "Original Road",
                    "lat": 0.001,
                    "lng": 0.0,
                    "distance_meters": 111,
                    "rating": 4.1,
                    "user_ratings_total": 120,
                    "types": ["restaurant"],
                    "provider_id": "orig",
                },
                "category": "restaurant",
                "time_block_start": "19:41",
                "time_block_end": "20:41",
                "travel_to_next_minutes": 1,
                "travel_mode": "walking",
                "why_this_place": "Original pick.",
            },
            {
                "place": {
                    "name": "Next Place",
                    "address": "Next Road",
                    "lat": 0.002,
                    "lng": 0.0,
                    "distance_meters": 222,
                    "rating": 4.4,
                    "user_ratings_total": 140,
                    "types": ["bar"],
                    "provider_id": "next",
                },
                "category": "bar",
                "time_block_start": "20:42",
                "time_block_end": "21:27",
                "travel_to_next_minutes": None,
                "travel_mode": None,
                "why_this_place": "Next pick.",
            },
        ],
        "total_duration_minutes": 147,
        "total_cost_estimate": "mid",
        "narrative": "A test route.",
        "created_at": "2026-05-04T00:00:00",
    }


def test_stop_alternatives_returns_top_three_and_filters_existing_places() -> None:
    class SwapProvider(FakeProvider):
        async def nearby_by_type(
            self,
            *,
            lat: float,
            lng: float,
            radius_meters: int,
            place_type: str,
            target_count: int | None = None,
        ) -> list[RawPlace]:
            self.nearby_types.append(place_type)
            return [
                RawPlace("orig", "Original Dinner", "Original Road", 0.001, 0.0, 4.9, ["restaurant"], 500),
                RawPlace("next", "Next Place", "Next Road", 0.002, 0.0, 4.9, ["restaurant"], 500),
                RawPlace("alt_best", "Best Bistro", "A Road", 0.0005, 0.0, 4.8, ["restaurant"], 800),
                RawPlace("alt_close", "Close Bistro", "B Road", 0.0004, 0.0, 4.3, ["restaurant"], 200),
                RawPlace("alt_far", "Far Bistro", "C Road", 0.003, 0.0, 4.9, ["restaurant"], 900),
                RawPlace("alt_fourth", "Fourth Bistro", "D Road", 0.004, 0.0, 4.0, ["restaurant"], 100),
            ]

    settings = get_settings()
    provider = SwapProvider()
    svc = NearbyPlacesService(provider, settings)
    app.dependency_overrides[get_nearby_places_service] = lambda: svc
    try:
        with TestClient(app) as c:
            res = c.post(
                "/api/quest/11111111-1111-4111-8111-111111111111/stop/1/alternatives",
                json=_quest_payload(),
            )
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 200
    body = res.json()
    assert len(body) == 3
    provider_ids = {stop["place"]["provider_id"] for stop in body}
    assert "orig" not in provider_ids
    assert "next" not in provider_ids
    assert all(stop["category"] == "restaurant" for stop in body)
    assert all(set(stop["delta"]) == {"cost_change", "time_change_minutes", "distance_change_meters"} for stop in body)
    assert body[0]["time_block_start"] == "19:41:00"
    assert body[0]["time_block_end"] == "20:41:00"
    assert body[0]["travel_to_next_minutes"] is not None
    assert provider.geocode_queries == ["0.0,0.0"]
    assert provider.nearby_types == ["restaurant"]


def test_stop_alternatives_rejects_unmapped_category() -> None:
    payload = _quest_payload()
    payload["stops"][1]["category"] = "attraction"
    payload["stops"][1]["place"]["types"] = ["point_of_interest"]

    settings = get_settings()
    svc = NearbyPlacesService(FakeProvider(), settings)
    app.dependency_overrides[get_nearby_places_service] = lambda: svc
    try:
        with TestClient(app) as c:
            res = c.post(
                "/api/quest/11111111-1111-4111-8111-111111111111/stop/1/alternatives",
                json=payload,
            )
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 422
