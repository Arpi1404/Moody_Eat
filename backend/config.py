"""Environment-driven settings for the Places API."""

from functools import lru_cache

from pydantic import Field
from pydantic.alias_generators import to_snake
from pydantic.fields import AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    google_places_api_key: str = Field(default="", validation_alias="GOOGLE_PLACES_API_KEY")

    default_radius_meters: int = Field(default=3000, ge=100, validation_alias="DEFAULT_RADIUS_METERS")
    max_radius_meters: int = Field(default=10000, ge=100, validation_alias="MAX_RADIUS_METERS")
    max_limit: int = Field(default=20, ge=1, le=20, validation_alias="MAX_LIMIT")

    request_timeout_seconds: float = Field(default=6.0, ge=1.0, validation_alias="PLACES_REQUEST_TIMEOUT_SECONDS")
    provider_max_retries: int = Field(default=1, ge=0, le=5, validation_alias="PLACES_PROVIDER_MAX_RETRIES")
    max_nearby_pages: int = Field(default=1, ge=1, le=3, validation_alias="PLACES_MAX_NEARBY_PAGES")
    category_concurrency: int = Field(default=3, ge=1, le=8, validation_alias="PLACES_CATEGORY_CONCURRENCY")

    cache_ttl_seconds: int = Field(default=600, ge=60, validation_alias="PLACES_CACHE_TTL_SECONDS")
    rate_limit_per_minute: int = Field(default=60, ge=0, validation_alias="PLACES_RATE_LIMIT_PER_MINUTE")
    rate_limit_enabled: bool = Field(default=True, validation_alias="PLACES_RATE_LIMIT_ENABLED")


@lru_cache
def get_settings() -> Settings:
    return Settings()
