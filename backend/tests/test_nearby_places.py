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
    ) -> list[RawPlace]:
        self.nearby_types.append(place_type)
        if self.empty_nearby:
            return []
        base = [
            RawPlace("p_far", "Far Cafe", "Road 1", 0.01, 0.0, 4.0, ["cafe"]),
            RawPlace("p_near", "Near Cafe", "Road 2", 0.001, 0.0, 4.5, ["cafe"]),
        ]
        if self.duplicate_across_types and place_type == "restaurant":
            return [
                RawPlace("p_near", "Near Cafe", "Road 2", 0.001, 0.0, 4.5, ["restaurant"]),
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
        ) -> list[RawPlace]:
            self.nearby_types.append(place_type)
            return [
                RawPlace("restaurant_1", "Dinner Point", "Road", 0.001, 0.0, 4.8, ["restaurant"]),
                RawPlace("cafe_1", "Brewed Awakenings", "Road", 0.001, 0.0, 4.3, ["cafe"]),
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
