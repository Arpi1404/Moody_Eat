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
