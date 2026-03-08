import pytest

import app.application.ema_scanner.service as scanner_module
from app.application.ema_scanner.service import EmaScannerService
from app.domain.ema_scanner.models import EmaScannerConfig
from app.domain.portfolio.models import MarketCandle


class FakeBinanceClient:
    def __init__(self, candles_by_symbol, price_by_symbol=None):
        self._candles_by_symbol = {
            self._normalize_symbol(symbol): list(candles)
            for symbol, candles in candles_by_symbol.items()
        }
        self._price_by_symbol = {
            self._normalize_symbol(symbol): price
            for symbol, price in (price_by_symbol or {}).items()
        }

    def fetch_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
        start_time_ms: int | None = None,
    ):
        del timeframe, start_time_ms
        candles = self._candles_by_symbol.get(self._normalize_symbol(symbol), [])
        return list(candles[-limit:])

    def fetch_ticker_price(self, symbol: str):
        return self._price_by_symbol.get(self._normalize_symbol(symbol))

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        return symbol.replace("/", "").upper()


class FakePortfolioService:
    async def get_active_connector(self):
        return None


@pytest.fixture(autouse=True)
def _no_interval_delay(monkeypatch):
    monkeypatch.setattr(scanner_module, "_EMA_INTERVAL_DELAY_SEC", 0)


@pytest.mark.asyncio
async def test_ema_scanner_detects_signal():
    candles = [
        MarketCandle(1, 10, 10, 10, 10, 0),
        MarketCandle(2, 10, 10, 10, 10, 0),
        MarketCandle(3, 10, 10, 10, 10, 0),
    ]
    service = EmaScannerService(
        FakePortfolioService(),
        binance_client=FakeBinanceClient({"BTCUSDT": candles}, {"BTCUSDT": 10}),
    )

    config = EmaScannerConfig(
        assets=["btc"],
        timeframes=["15m"],
        ema_lengths=[3],
        tolerance_pct=0.5,
        min_candles=3,
        candles_multiplier=1,
        max_candles=3,
    )

    signals = await service.scan(config)

    assert len(signals) >= 1
    ema_signals = [s for s in signals if s.indicator == "EMA"]
    assert len(ema_signals) == 1
    signal = ema_signals[0]
    assert signal.symbol == "BTC/USDT"
    assert signal.parameter == "EMA-3"
    assert signal.price == 10


@pytest.mark.asyncio
async def test_ema_scanner_skips_short_series():
    candles = [
        MarketCandle(1, 10, 10, 10, 10, 0),
        MarketCandle(2, 10, 10, 10, 10, 0),
    ]
    service = EmaScannerService(
        FakePortfolioService(),
        binance_client=FakeBinanceClient({"ETHUSDT": candles}, {"ETHUSDT": 10}),
    )

    config = EmaScannerConfig(
        assets=["ETH"],
        timeframes=["1h"],
        ema_lengths=[3],
        tolerance_pct=0.5,
        min_candles=2,
        candles_multiplier=1,
        max_candles=2,
    )

    signals = await service.scan(config)
    assert signals == []


@pytest.mark.asyncio
async def test_ema_scanner_uses_candle_close_when_live_price_unavailable():
    candles = [
        MarketCandle(1, 10, 10, 10, 10, 0),
        MarketCandle(2, 10, 10, 10, 10, 0),
        MarketCandle(3, 10, 10, 10, 10, 0),
    ]
    service = EmaScannerService(
        FakePortfolioService(),
        binance_client=FakeBinanceClient({"BTCUSDT": candles}, {"BTCUSDT": None}),
    )

    config = EmaScannerConfig(
        assets=["BTC"],
        timeframes=["15m"],
        ema_lengths=[3],
        tolerance_pct=1.0,
        min_candles=3,
        candles_multiplier=1,
        max_candles=3,
    )

    signals = await service.scan(config)
    assert len([signal for signal in signals if signal.indicator == "EMA"]) == 1


@pytest.mark.asyncio
async def test_ema_scanner_emits_bb_signals():
    candles = [MarketCandle(i, 10, 10, 10, 10, 0) for i in range(1, 21)]
    service = EmaScannerService(
        FakePortfolioService(),
        binance_client=FakeBinanceClient({"BTCUSDT": candles}, {"BTCUSDT": 10}),
    )

    config = EmaScannerConfig(
        assets=["BTC"],
        timeframes=["1h"],
        ema_lengths=[3],
        tolerance_pct=0.5,
        min_candles=20,
        candles_multiplier=1,
        max_candles=20,
    )

    signals = await service.scan(config)
    bb_signals = [s for s in signals if s.indicator == "BB"]
    assert len(bb_signals) == 2
    params = {s.parameter for s in bb_signals}
    assert params == {"BB-Upper", "BB-Lower"}


@pytest.mark.asyncio
async def test_ema_scanner_invokes_asset_callback_per_asset():
    candles = [
        MarketCandle(1, 10, 10, 10, 10, 0),
        MarketCandle(2, 10, 10, 10, 10, 0),
        MarketCandle(3, 10, 10, 10, 10, 0),
    ]
    service = EmaScannerService(
        FakePortfolioService(),
        binance_client=FakeBinanceClient(
            {"BTCUSDT": candles, "ETHUSDT": candles},
            {"BTCUSDT": 10, "ETHUSDT": 10},
        ),
    )

    config = EmaScannerConfig(
        assets=["BTC", "ETH"],
        timeframes=["15m"],
        ema_lengths=[3],
        tolerance_pct=0.5,
        min_candles=3,
        candles_multiplier=1,
        max_candles=3,
    )

    callbacks: list[tuple[str, int]] = []

    async def on_asset(symbol: str, asset_signals, charts):
        del charts
        callbacks.append((symbol, len(asset_signals)))

    signals = await service.scan(config, asset_callback=on_asset)

    assert len(signals) == 2
    assert callbacks == [("BTC/USDT", 1), ("ETH/USDT", 1)]

