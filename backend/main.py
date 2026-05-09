import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from rate_limit import NearbyPlacesRateLimitMiddleware
from routes import router as quest_router

app = FastAPI(title="Travel Planner API")

_DEV_ORIGINS = [
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://localhost:3000",
]

# Production origins come from ALLOWED_ORIGINS env var (comma-separated).
# Falls back to local dev ports when unset.
_env_origins = os.environ.get("ALLOWED_ORIGINS", "").strip()
origins = (
    [o.strip() for o in _env_origins.split(",") if o.strip()]
    if _env_origins
    else _DEV_ORIGINS
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(NearbyPlacesRateLimitMiddleware)

app.include_router(quest_router)


@app.get("/")
async def root():
    return {"message": "Travel Planner API is running"}

