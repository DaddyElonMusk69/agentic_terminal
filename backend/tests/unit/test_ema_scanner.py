import pytest

from app.application.ema_scanner.service import EmaScannerService
from app.domain.ema_scanner.models import EmaScannerConfig
from app.domain.portfolio.models import MarketCandle, MarketQuote


class FakeConnector:
    def __init__(self, candles, price=None):
        self._candles = candles
        self._price = price

    async def fetch_candles(self, symbol: str, timeframe: str, limit: int):
        return self._candles

    async def fetch_ticker_price(self, symbol: str):
        return self._price

    async def fetch_ticker_quote(self, symbol: str):
        if self._price is None:
            return None
        return MarketQuote(price=self._price, change_percent=None)

    async def fetch_ticker_quotes(self, symbols):
        if self._price is None:
            return {}
        return {symbol: MarketQuote(price=self._price, change_percent=None) for symbol in symbols}


class FakePortfolioService:
    def __init__(self, connector):
        self._connector = connector

    async def get_active_connector(self):
        return self._connector


@pytest.mark.asyncio
async def test_ema_scanner_detects_signal():
    candles = [
        MarketCandle(1, 10, 10, 10, 10, 0),
        MarketCandle(2, 10, 10, 10, 10, 0),
        MarketCandle(3, 10, 10, 10, 10, 0),
    ]
    service = EmaScannerService(FakePortfolioService(FakeConnector(candles, price=10)))

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
    service = EmaScannerService(FakePortfolioService(FakeConnector(candles, price=10)))

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
async def test_ema_scanner_requires_live_price_when_enabled():
    candles = [
        MarketCandle(1, 10, 10, 10, 10, 0),
        MarketCandle(2, 10, 10, 10, 10, 0),
        MarketCandle(3, 10, 10, 10, 10, 0),
    ]
    service = EmaScannerService(FakePortfolioService(FakeConnector(candles, price=None)))

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
    assert signals == []


@pytest.mark.asyncio
async def test_ema_scanner_emits_bb_signals():
    candles = [MarketCandle(i, 10, 10, 10, 10, 0) for i in range(1, 21)]
    service = EmaScannerService(FakePortfolioService(FakeConnector(candles, price=10)))

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
