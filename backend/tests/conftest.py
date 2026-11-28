import pytest


@pytest.fixture(autouse=True)
def no_network_weather(monkeypatch):
    """Keep the suite offline: weather defaults to 'unknown' (fail-open path).

    Tests that exercise rain gating re-patch quest_generator.rain_expected
    themselves.
    """
    async def _unknown(*args, **kwargs):
        return None

    monkeypatch.setattr("quest_generator.rain_expected", _unknown)
    # And the place's clock (from the same forecast call) is unknown, so the
    # chosen day is trusted as it is and no start is moved.
    monkeypatch.setattr("quest_generator.place_utc_offset", _unknown)


@pytest.fixture(autouse=True)
def no_text_model(monkeypatch):
    """Keep the suite from calling a real text model, whatever is in the
    developer's environment or .env. Tests of the model patch these back."""
    from config import get_settings

    for name in ("TEXT_MODEL_URL", "TEXT_MODEL_NAME", "TEXT_MODEL_API_KEY"):
        monkeypatch.setenv(name, "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
