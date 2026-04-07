from __future__ import annotations


class PlacesProviderError(Exception):
    """Base class for provider failures."""

    def __init__(self, message: str, *, provider_status: str | None = None) -> None:
        super().__init__(message)
        self.provider_status = provider_status


class LocationNotFoundError(PlacesProviderError):
    """Geocoding returned no results."""

    pass


class ProviderAuthError(PlacesProviderError):
    """Invalid API key or access denied."""

    pass


class ProviderQuotaError(PlacesProviderError):
    """Quota exceeded or billing issue."""

    pass


class ProviderTimeoutError(PlacesProviderError):
    """Request timed out."""

    pass
