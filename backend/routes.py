from fastapi import APIRouter, HTTPException

from data import QUEST_DATA
from models import QuestRequest, QuestResponse

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

