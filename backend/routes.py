from fastapi import APIRouter, Depends, HTTPException

from data import QUEST_DATA
from deps import get_nearby_places_service
from models import NearbyPlacesRequest, NearbyPlacesResponse, QuestRequest, QuestResponse
from services.nearby_places_service import NearbyPlacesService, map_provider_error
from services.places_exceptions import PlacesProviderError

router = APIRouter()


@router.post("/api/generate-quest", response_model=QuestResponse)
async def generate_quest(payload: QuestRequest) -> QuestResponse:
  location_key = payload.location.strip().lower()
  mood_key = payload.mood.strip().lower()

  if location_key not in QUEST_DATA:
      raise HTTPException(
          status_code=400,
          detail={
              "message": "Unsupported location for this proof of concept.",
              "supported_locations": list(QUEST_DATA.keys()),
          },
      )

  location_moods = QUEST_DATA[location_key]
  if mood_key not in location_moods:
      raise HTTPException(
          status_code=400,
          detail={
              "message": "Unsupported mood for this location in this proof of concept.",
              "supported_moods": list(location_moods.keys()),
          },
      )

  cafes = location_moods[mood_key][:3]
  return QuestResponse(location=location_key, mood=mood_key, cafes=cafes)


@router.post("/api/places/nearby", response_model=NearbyPlacesResponse)
async def nearby_places(
    payload: NearbyPlacesRequest,
    service: NearbyPlacesService = Depends(get_nearby_places_service),
) -> NearbyPlacesResponse:
    try:
        return await service.search(payload)
    except PlacesProviderError as exc:
        status_code, message = map_provider_error(exc)
        detail: dict[str, object] = {"message": message}
        if exc.provider_status:
            detail["provider_status"] = exc.provider_status
        raise HTTPException(status_code=status_code, detail=detail) from exc

