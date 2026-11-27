import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from creator_routes import router as creator_router
from rate_limit import NearbyPlacesRateLimitMiddleware
from routes import router as quest_router

# Uvicorn only configures its own loggers; without this, the app's telemetry
# (places_filter, quest_candidate_viability, quest_price_profile) is dropped.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
# httpx logs every request URL at INFO, and the Geocoding API takes the key as
# a query param, so INFO would write GOOGLE_PLACES_API_KEY into the logs.
logging.getLogger("httpx").setLevel(logging.WARNING)

# Error monitoring is opt-in: set SENTRY_DSN in the deploy environment.
_sentry_dsn = os.environ.get("SENTRY_DSN", "").strip()
if _sentry_dsn:
    import sentry_sdk

    sentry_sdk.init(
        dsn=_sentry_dsn,
        environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
        traces_sample_rate=0.0,
        send_default_pii=False,
        # A frame's locals can hold a creator's key: the request scope carries
        # the Authorization header in a list, which no scrubbing by variable
        # name will find.
        include_local_variables=False,
    )

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

app.add_middleware(NearbyPlacesRateLimitMiddleware)

# Added last so that it wraps everything. A rate-limit reply without CORS
# headers cannot be read by the browser, which then reports a network failure
# instead of "too many requests".
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(quest_router)
app.include_router(creator_router)


@app.get("/")
async def root():
    return {"message": "Travel Planner API is running"}

