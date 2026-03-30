from datetime import datetime, timezone

import pytest

from app.application.market_settings import service as market_settings_service
from app.application.market_settings.service import MarketSettingsService


class StubMarketSettingsRepository:
    async def list_assets(self):
        return []

    async def list_us_stock_assets(self):
        return []

    async def list_intervals(self):
        return []

    async def add_asset(self, _symbol: str):
        return None

    async def add_us_stock_asset(self, _symbol: str):
        return None

    async def remove_asset(self, _symbol: str):
        return None

    async def remove_us_stock_asset(self, _symbol: str):
        return None

    async def add_interval(self, _interval: str):
        return None

    async def remove_interval(self, _interval: str):
        return None


@pytest.fixture(autouse=True)
def reset_market_calendar_caches():
    cache_clear = getattr(market_settings_service._load_us_stock_market_calendar, "cache_clear", None)
    if callable(cache_clear):
        cache_clear()
    cache_clear = getattr(
        market_settings_service._get_us_stock_market_session_bounds,
        "cache_clear",
        None,
    )
    if callable(cache_clear):
        cache_clear()
    market_settings_service._warned_missing_market_calendar = False
    yield
    cache_clear = getattr(market_settings_service._load_us_stock_market_calendar, "cache_clear", None)
    if callable(cache_clear):
        cache_clear()
    cache_clear = getattr(
        market_settings_service._get_us_stock_market_session_bounds,
        "cache_clear",
        None,
    )
    if callable(cache_clear):
        cache_clear()
    market_settings_service._warned_missing_market_calendar = False


def test_us_stock_market_open_during_regular_session(monkeypatch: pytest.MonkeyPatch):
    service = MarketSettingsService(StubMarketSettingsRepository())
    market_open = datetime(2026, 3, 27, 13, 30, tzinfo=timezone.utc)
    market_close = datetime(2026, 3, 27, 20, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(market_settings_service, "_load_us_stock_market_calendar", lambda: object())
    monkeypatch.setattr(
        market_settings_service,
        "_get_us_stock_market_session_bounds",
        lambda _session_date: (market_open, market_close),
    )

    is_open = service.is_us_stock_market_open(
        datetime(2026, 3, 27, 14, 0, tzinfo=timezone.utc)
    )

    assert is_open is True


def test_us_stock_market_closed_before_open(monkeypatch: pytest.MonkeyPatch):
    service = MarketSettingsService(StubMarketSettingsRepository())
    market_open = datetime(2026, 3, 27, 13, 30, tzinfo=timezone.utc)
    market_close = datetime(2026, 3, 27, 20, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(market_settings_service, "_load_us_stock_market_calendar", lambda: object())
    monkeypatch.setattr(
        market_settings_service,
        "_get_us_stock_market_session_bounds",
        lambda _session_date: (market_open, market_close),
    )

    is_open = service.is_us_stock_market_open(
        datetime(2026, 3, 27, 13, 29, tzinfo=timezone.utc)
    )

    assert is_open is False


def test_us_stock_market_closed_on_market_holiday(monkeypatch: pytest.MonkeyPatch):
    service = MarketSettingsService(StubMarketSettingsRepository())
    monkeypatch.setattr(market_settings_service, "_load_us_stock_market_calendar", lambda: object())
    monkeypatch.setattr(
        market_settings_service,
        "_get_us_stock_market_session_bounds",
        lambda _session_date: None,
    )

    is_open = service.is_us_stock_market_open(
        datetime(2026, 12, 25, 15, 0, tzinfo=timezone.utc)
    )

    assert is_open is False


def test_us_stock_market_falls_back_when_calendar_dependency_missing(
    monkeypatch: pytest.MonkeyPatch,
):
    service = MarketSettingsService(StubMarketSettingsRepository())
    monkeypatch.setattr(market_settings_service, "_load_us_stock_market_calendar", lambda: None)

    is_open = service.is_us_stock_market_open(
        datetime(2026, 3, 27, 14, 0, tzinfo=timezone.utc)
    )

    assert is_open is True
