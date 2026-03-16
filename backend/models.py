from pydantic import BaseModel


class QuestRequest(BaseModel):
    location: str
    mood: str


class Cafe(BaseModel):
    name: str
    address: str
    distance_minutes_walk: int
    vibe: str


class QuestResponse(BaseModel):
    location: str
    mood: str
    cafes: list[Cafe]

