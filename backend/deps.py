from fastapi import HTTPException

from services.google_places import GooglePlacesProvider
from services.nearby_places_service import NearbyPlacesService
from services.places_exceptions import ProviderAuthError

from config import get_settings


async def get_nearby_places_service() -> NearbyPlacesService:
    settings = get_settings()
    try:
        provider = GooglePlacesProvider(settings)
    except ProviderAuthError as exc:
        raise HTTPException(
            status_code=503,
            detail={"message": str(exc), "provider_status": exc.provider_status},
        ) from exc
    return NearbyPlacesService(provider, settings)
