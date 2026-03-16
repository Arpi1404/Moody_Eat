from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes import router as quest_router

app = FastAPI(title="Travel Planner API")

origins = [
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "*",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(quest_router)


@app.get("/name")
async def get_name():
    return {"name": "Traveler"}


@app.get("/")
async def root():
    return {"message": "Travel Planner API is running"}

