from datetime import datetime, timezone

import pytest

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
async def test_fetch_recent_completed_trades_groups_binance_fills_into_closed_positions():
    connector = _build_connector("binance")
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    class FakeClient:
        has = {"fetchMyTrades": True}
        markets = {"BTC/USDT:USDT": {"symbol": "BTC/USDT:USDT", "base": "BTC", "quote": "USDT", "swap": True}}
        options = {"defaultType": "swap"}

        async def fapiPrivateGetIncome(self, params):  # noqa: ANN001
            assert params["incomeType"] == "REALIZED_PNL"
            return [
                {"symbol": "BTCUSDT", "income": "2.0", "time": now_ms - 60_000},
                {"symbol": "BTCUSDT", "income": "6.0", "time": now_ms},
            ]

        async def fetch_my_trades(self, symbol=None, since=None, limit=None):  # noqa: ANN001
            assert symbol == "BTC/USDT:USDT"
            assert since is not None
            assert limit >= 200
            return [
                {
                    "symbol": "BTC/USDT:USDT",
                    "side": "buy",
                    "amount": 1.0,
                    "price": 100.0,
                    "timestamp": now_ms - 120_000,
                    "fee": {"cost": 0.0},
                    "info": {},
                },
                {
                    "symbol": "BTC/USDT:USDT",
                    "side": "sell",
                    "amount": 0.4,
                    "price": 105.0,
                    "timestamp": now_ms - 60_000,
                    "fee": {"cost": 0.0},
                    "info": {"realizedPnl": "2.0", "orderId": "close-a"},
                },
                {
                    "symbol": "BTC/USDT:USDT",
                    "side": "sell",
                    "amount": 0.6,
                    "price": 110.0,
                    "timestamp": now_ms,
                    "fee": {"cost": 0.0},
                    "info": {"realizedPnl": "6.0", "orderId": "close-b"},
                },
            ]

    connector._client = lambda: _AsyncContext(FakeClient())  # type: ignore[method-assign]

    completed = await connector.fetch_recent_completed_trades(limit=10)

    assert len(completed) == 1
    assert completed[0]["symbol"] == "BTC"
    assert completed[0]["direction"] == "long"
    assert completed[0]["entry_price"] == pytest.approx(100.0)
    assert completed[0]["exit_price"] == pytest.approx(108.0)
    assert completed[0]["pnl"] == pytest.approx(8.0)
    assert completed[0]["duration_minutes"] == 2

