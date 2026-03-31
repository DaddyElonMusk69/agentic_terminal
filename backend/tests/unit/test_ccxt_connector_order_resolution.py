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
async def test_fetch_open_orders_resolves_bare_symbol_to_market_symbol():
    connector = _build_connector("binance")

    class FakeClient:
        has = {"fetchOpenOrders": True}
        markets = {
            "BTC/USDT:USDT": {"symbol": "BTC/USDT:USDT", "base": "BTC", "quote": "USDT", "swap": True, "id": "BTCUSDT"}
        }

        def __init__(self) -> None:
            self.received_symbols: list[str] = []

        async def fetch_open_orders(self, symbol=None):  # noqa: ANN001
            self.received_symbols.append(symbol)
            return [{"id": "1", "symbol": symbol, "status": "open"}]

    client = FakeClient()
    connector._client = lambda: _AsyncContext(client)  # type: ignore[method-assign]

    orders = await connector.fetch_open_orders(["BTC"])

    assert client.received_symbols == ["BTC/USDT:USDT"]
    assert orders[0]["symbol"] == "BTC/USDT:USDT"


@pytest.mark.asyncio
async def test_fetch_order_resolves_bare_symbol_to_market_symbol():
    connector = _build_connector("binance")

    class FakeClient:
        markets = {
            "BTC/USDT:USDT": {"symbol": "BTC/USDT:USDT", "base": "BTC", "quote": "USDT", "swap": True, "id": "BTCUSDT"}
        }

        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        async def fetch_order(self, order_id, symbol):  # noqa: ANN001
            self.calls.append((order_id, symbol))
            return {"id": order_id, "symbol": symbol}

    client = FakeClient()
    connector._client = lambda: _AsyncContext(client)  # type: ignore[method-assign]

    order = await connector.fetch_order("ord-1", "BTC")

    assert client.calls == [("ord-1", "BTC/USDT:USDT")]
    assert order == {"id": "ord-1", "symbol": "BTC/USDT:USDT"}


@pytest.mark.asyncio
async def test_cancel_order_resolves_bare_symbol_to_market_symbol():
    connector = _build_connector("binance")

    class FakeClient:
        markets = {
            "BTC/USDT:USDT": {"symbol": "BTC/USDT:USDT", "base": "BTC", "quote": "USDT", "swap": True, "id": "BTCUSDT"}
        }

        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        async def cancel_order(self, order_id, symbol):  # noqa: ANN001
            self.calls.append((order_id, symbol))
            return {"id": order_id, "symbol": symbol, "status": "canceled"}

    client = FakeClient()
    connector._client = lambda: _AsyncContext(client)  # type: ignore[method-assign]

    result = await connector.cancel_order("ord-2", "BTC")

    assert client.calls == [("ord-2", "BTC/USDT:USDT")]
    assert result == {"id": "ord-2", "symbol": "BTC/USDT:USDT", "status": "canceled"}
