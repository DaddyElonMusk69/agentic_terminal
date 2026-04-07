from datetime import datetime, timezone

import pytest

from app.application.quant_scanner.service import QuantScannerService
from app.domain.portfolio.models import (
    FundingRateSnapshot,
    MarketCandle,
    MarketDataPoint,
    OrderBookLevel,
    OrderBookSnapshot,
)
from app.domain.quant_scanner.models import QuantScannerConfig


class StubDisabledNetflowService:
    def __init__(self) -> None:
        self.fetch_calls = 0
        self.build_calls = 0

    def is_enabled(self) -> bool:
        return False

    def is_configured(self) -> bool:
        return False

    async def fetch_raw(self, symbol: str):  # noqa: ANN001
        self.fetch_calls += 1
        return {"unexpected": symbol}

    def build_metrics(self, raw_data, timeframe):  # noqa: ANN001
        self.build_calls += 1
        return {"unexpected": timeframe, "raw_data": raw_data}


class StubBinanceClient:
    def __init__(self) -> None:
        self.last_error = None

    def fetch_order_book(self, symbol: str, limit: int):  # noqa: ARG002
        return OrderBookSnapshot(
            symbol=symbol,
            timestamp_ms=1700000000000,
            bids=[OrderBookLevel(price=100.0, size=10.0)],
            asks=[OrderBookLevel(price=100.5, size=8.0)],
        )

    def fetch_funding_rate(self, symbol: str):  # noqa: ARG002
        return FundingRateSnapshot(
            rate=0.0001,
            timestamp_ms=1700000000000,
            next_funding_time_ms=1700003600000,
            mark_price=100.25,
        )

    def fetch_candles(self, symbol: str, timeframe: str, limit: int):  # noqa: ARG002
        candles: list[MarketCandle] = []
        base = 100.0
        for idx in range(limit):
            close = base + idx * 0.2
            candles.append(
                MarketCandle(
                    timestamp_ms=1700000000000 + idx * 60_000,
                    open=close - 0.1,
                    high=close + 0.2,
                    low=close - 0.2,
                    close=close,
                    volume=10.0 + idx,
                )
            )
        return candles

    def fetch_open_interest_history(self, symbol: str, timeframe: str, limit: int):  # noqa: ARG002
        return [
            MarketDataPoint(
                timestamp_ms=1700000000000 + idx * 60_000,
                value=1000.0 + idx * 20.0,
            )
            for idx in range(limit)
        ]

    def consume_last_error(self):
        return self.last_error


class StubPortfolioService:
    pass


@pytest.mark.asyncio
async def test_quant_scanner_skips_disabled_netflow_service():
    netflow_service = StubDisabledNetflowService()
    scanner = QuantScannerService(
        portfolio_service=StubPortfolioService(),
        netflow_service=netflow_service,
        binance_client=StubBinanceClient(),
    )
    config = QuantScannerConfig(
        assets=["BTC"],
        timeframes=["1h"],
        quote_asset="USDT",
    )

    logs: list[str] = []

    async def log_callback(message: str, log_type: str):  # noqa: ANN001
        logs.append(message)

    snapshots = await scanner.scan(config, limit=6, log_callback=log_callback)

    assert len(snapshots) == 1
    assert snapshots[0].symbol == "BTC/USDT"
    assert snapshots[0].timeframe == "1h"
    assert snapshots[0].netflow is None
    assert netflow_service.fetch_calls == 0
    assert netflow_service.build_calls == 0
    assert any("netflow: disabled (NofXOS deprecated)" in message for message in logs)
