from datetime import datetime, timedelta, timezone

import pytest
from zoneinfo import ZoneInfo

from app.domain.portfolio.models import DailyPnlSnapshot
from app.infrastructure.exchange.ccxt_connector import CCXTConfig, CCXTConnector


class _AsyncContext:
    def __init__(self, client) -> None:
        self._client = client

    async def __aenter__(self):
        return self._client

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


def _build_connector(exchange_id: str = "binance") -> CCXTConnector:
    connector = object.__new__(CCXTConnector)
    connector._config = CCXTConfig(  # type: ignore[attr-defined]
        exchange_id=exchange_id,
        api_key="key",
        api_secret="secret",
        passphrase=None,
        is_testnet=False,
    )
    return connector


@pytest.mark.asyncio
async def test_fetch_daily_pnl_binance_falls_back_when_income_snapshot_is_empty(monkeypatch):
    connector = _build_connector("binance")
    client = object()

    connector._client = lambda: _AsyncContext(client)  # type: ignore[method-assign]

    async def fake_binance_daily_pnl(inner_client, start_timestamp_ms):  # noqa: ANN001
        assert inner_client is client
        assert isinstance(start_timestamp_ms, int)
        return DailyPnlSnapshot(realized_pnl=0.0, trade_count=0, fills=[], exchange="binance")

    async def fake_trade_reconstruction(inner_client, start_timestamp_ms):  # noqa: ANN001
        assert inner_client is client
        assert isinstance(start_timestamp_ms, int)
        return DailyPnlSnapshot(
            realized_pnl=12.5,
            trade_count=2,
            fills=[{"symbol": "BTCUSDT"}],
            exchange="binance",
        )

    monkeypatch.setattr(connector, "_get_binance_daily_pnl", fake_binance_daily_pnl)
    monkeypatch.setattr(connector, "_get_daily_pnl_from_trades", fake_trade_reconstruction)

    snapshot = await connector.fetch_daily_pnl()

    assert snapshot.realized_pnl == 12.5
    assert snapshot.trade_count == 2


@pytest.mark.asyncio
async def test_fetch_daily_pnl_uses_local_timezone_day_boundary(monkeypatch):
    connector = _build_connector("binance")
    client = object()
    connector._client = lambda: _AsyncContext(client)  # type: ignore[method-assign]

    class _Settings:
        local_timezone = "Asia/Shanghai"

    fixed_now_utc = datetime(2026, 3, 20, 18, 30, tzinfo=timezone.utc)
    fixed_now_local = fixed_now_utc.astimezone(ZoneInfo("Asia/Shanghai"))
    expected_start_local = fixed_now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    expected_start_ms = int(expected_start_local.astimezone(timezone.utc).timestamp() * 1000)
    captured = {}

    class _FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fixed_now_utc.replace(tzinfo=None)
            return fixed_now_utc.astimezone(tz)

    async def fake_binance_daily_pnl(inner_client, start_timestamp_ms):  # noqa: ANN001
        captured["start_timestamp_ms"] = start_timestamp_ms
        return DailyPnlSnapshot(realized_pnl=5.0, trade_count=1, fills=[{"symbol": "BTCUSDT"}], exchange="binance")

    monkeypatch.setattr("app.infrastructure.exchange.ccxt_connector.get_settings", lambda: _Settings())
    monkeypatch.setattr("app.infrastructure.exchange.ccxt_connector.datetime", _FakeDateTime)
    monkeypatch.setattr(connector, "_get_binance_daily_pnl", fake_binance_daily_pnl)

    snapshot = await connector.fetch_daily_pnl()

    assert snapshot.realized_pnl == 5.0
    assert captured["start_timestamp_ms"] == expected_start_ms


@pytest.mark.asyncio
async def test_daily_pnl_reconstruction_can_fetch_trades_without_pre_discovered_symbols():
    connector = _build_connector("bybit")
    since_ms = int((datetime.now(timezone.utc) - timedelta(hours=4)).timestamp() * 1000)

    class FakeClient:
        has = {
            "fetchPositions": False,
            "fetchClosedOrders": False,
            "fetchMyTrades": True,
        }

        async def fetch_my_trades(self, symbol=None, since=None, limit=None):  # noqa: ANN001
            assert symbol is None
            assert since == since_ms
            assert limit == 200
            return [
                {
                    "symbol": "BTC/USDT:USDT",
                    "side": "buy",
                    "amount": 1,
                    "price": 100,
                    "cost": 100,
                    "timestamp": since_ms + 1000,
                    "fee": {"cost": 0},
                },
                {
                    "symbol": "BTC/USDT:USDT",
                    "side": "sell",
                    "amount": 1,
                    "price": 110,
                    "cost": 110,
                    "timestamp": since_ms + 2000,
                    "fee": {"cost": 0},
                },
            ]

    snapshot = await connector._get_daily_pnl_from_trades(FakeClient(), since_ms)

    assert snapshot.realized_pnl == 10.0
    assert snapshot.trade_count == 1
    assert len(snapshot.fills) == 2
