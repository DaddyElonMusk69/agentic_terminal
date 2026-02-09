import pytest

from app.application.monitored_assets.service import MonitoredAssetsService
from app.domain.dynamic_assets.models import DynamicAssetsState


class StubMarketSettingsService:
    def __init__(self, assets):
        self.assets = assets
        self.calls = 0

    async def list_assets(self):
        self.calls += 1
        return list(self.assets)


class StubDynamicAssetsService:
    def __init__(self, state: DynamicAssetsState):
        self.state = state
        self.calls = 0

    async def resolve_assets(self, force_refresh: bool = False) -> DynamicAssetsState:
        self.calls += 1
        return self.state


class StubPositionRepository:
    async def list_assets(self):
        return []

    async def add_assets(self, _symbols):
        return None

    async def sync_assets(self, _symbols):
        return None


@pytest.mark.asyncio
async def test_uses_dynamic_assets_when_available():
    dynamic_state = DynamicAssetsState(
        assets=["BTCUSDT", "eth/usdt", "SOL-PERP"],
        enabled=True,
        binance_active=True,
        is_stale=False,
    )
    market_settings = StubMarketSettingsService(["ADAUSDT"])
    service = MonitoredAssetsService(
        market_settings=market_settings,
        dynamic_assets=StubDynamicAssetsService(dynamic_state),
        position_repository=StubPositionRepository(),
    )

    assets = await service.list_assets(include_positions=False)

    assert assets == ["BTC", "ETH", "SOL"]
    assert market_settings.calls == 0


@pytest.mark.asyncio
async def test_falls_back_to_manual_assets_when_dynamic_stale():
    dynamic_state = DynamicAssetsState(
        assets=[],
        enabled=True,
        binance_active=True,
        is_stale=True,
    )
    market_settings = StubMarketSettingsService(["ADAUSDT", "BTC/USDT"])
    service = MonitoredAssetsService(
        market_settings=market_settings,
        dynamic_assets=StubDynamicAssetsService(dynamic_state),
        position_repository=StubPositionRepository(),
    )

    assets = await service.list_assets(include_positions=False)

    assert assets == ["ADA", "BTC"]
    assert market_settings.calls == 1


@pytest.mark.asyncio
async def test_falls_back_to_manual_assets_when_dynamic_unavailable():
    dynamic_state = DynamicAssetsState(
        assets=[],
        enabled=True,
        binance_active=True,
        is_stale=False,
    )
    market_settings = StubMarketSettingsService(["XRPUSDT"])
    service = MonitoredAssetsService(
        market_settings=market_settings,
        dynamic_assets=StubDynamicAssetsService(dynamic_state),
        position_repository=StubPositionRepository(),
    )

    assets = await service.list_assets(include_positions=False)

    assert assets == ["XRP"]
    assert market_settings.calls == 1
