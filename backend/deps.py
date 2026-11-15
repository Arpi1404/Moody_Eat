from fastapi import HTTPException

from services.google_places import GooglePlacesProvider
from services.nearby_places_service import NearbyPlacesService
from services.places_exceptions import ProviderAuthError

from config import get_settings


def _build_provider() -> GooglePlacesProvider:
    try:
        return GooglePlacesProvider(get_settings())
    except ProviderAuthError as exc:
        raise HTTPException(
            status_code=503,
            detail={"message": str(exc), "provider_status": exc.provider_status},
        ) from exc


async def get_places_provider() -> GooglePlacesProvider:
    return _build_provider()


async def get_nearby_places_service() -> NearbyPlacesService:
    return NearbyPlacesService(_build_provider(), get_settings())
