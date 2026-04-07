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
            return [{"id": "1", "symbol": "BTC/USDT:USDT", "status": "open"}]

    client = FakeClient()
    connector._client = lambda: _AsyncContext(client)  # type: ignore[method-assign]

    orders = await connector.fetch_open_orders(["BTC"])

    assert client.received_symbols == [None]
    assert orders[0]["symbol"] == "BTC/USDT:USDT"


@pytest.mark.asyncio
async def test_fetch_open_orders_falls_back_to_per_symbol_when_fetch_all_fails():
    connector = _build_connector("binance")

    class FakeClient:
        has = {"fetchOpenOrders": True}
        markets = {
            "BTC/USDT:USDT": {"symbol": "BTC/USDT:USDT", "base": "BTC", "quote": "USDT", "swap": True, "id": "BTCUSDT"}
        }

        def __init__(self) -> None:
            self.received_symbols: list[str | None] = []

        async def fetch_open_orders(self, symbol=None):  # noqa: ANN001
            self.received_symbols.append(symbol)
            if symbol is None:
                raise RuntimeError("fetch all unsupported")
            return [{"id": "1", "symbol": symbol, "status": "open"}]

    client = FakeClient()
    connector._client = lambda: _AsyncContext(client)  # type: ignore[method-assign]

    orders = await connector.fetch_open_orders(["BTC"])

    assert client.received_symbols == [None, "BTC/USDT:USDT"]
    assert len(orders) == 1
    assert orders[0]["symbol"] == "BTC/USDT:USDT"


@pytest.mark.asyncio
async def test_fetch_open_orders_filters_binance_algo_orders_after_single_fetch():
    connector = _build_connector("binance")

    class FakeClient:
        has = {"fetchOpenOrders": True}
        markets = {
            "BTC/USDT:USDT": {"symbol": "BTC/USDT:USDT", "base": "BTC", "quote": "USDT", "swap": True, "id": "BTCUSDT"},
            "ETH/USDT:USDT": {"symbol": "ETH/USDT:USDT", "base": "ETH", "quote": "USDT", "swap": True, "id": "ETHUSDT"},
        }
        markets_by_id = {
            "BTCUSDT": {"symbol": "BTC/USDT:USDT"},
            "ETHUSDT": {"symbol": "ETH/USDT:USDT"},
        }

        def __init__(self) -> None:
            self.algo_calls = 0

        async def fetch_open_orders(self, symbol=None):  # noqa: ANN001
            return []

        async def fapiPrivateGetOpenAlgoOrders(self, params=None):  # noqa: N802, ANN001
            self.algo_calls += 1
            return [
                {"algoId": "a1", "symbol": "BTCUSDT", "orderType": "STOP_MARKET", "triggerPrice": "100"},
                {"algoId": "a2", "symbol": "ETHUSDT", "orderType": "STOP_MARKET", "triggerPrice": "100"},
            ]

    client = FakeClient()
    connector._client = lambda: _AsyncContext(client)  # type: ignore[method-assign]

    orders = await connector.fetch_open_orders(["BTC"])

    assert client.algo_calls == 1
    assert len(orders) == 1
    assert orders[0]["symbol"] == "BTC/USDT:USDT"


@pytest.mark.asyncio
async def test_fetch_open_orders_skips_binance_algo_orders_when_disabled():
    connector = _build_connector("binance")

    class FakeClient:
        has = {"fetchOpenOrders": True}
        markets = {
            "BTC/USDT:USDT": {"symbol": "BTC/USDT:USDT", "base": "BTC", "quote": "USDT", "swap": True, "id": "BTCUSDT"},
        }

        def __init__(self) -> None:
            self.algo_calls = 0

        async def fetch_open_orders(self, symbol=None):  # noqa: ANN001
            return [{"id": "1", "symbol": "BTC/USDT:USDT", "status": "open"}]

        async def fapiPrivateGetOpenAlgoOrders(self, params=None):  # noqa: N802, ANN001
            self.algo_calls += 1
            return [
                {"algoId": "a1", "symbol": "BTCUSDT", "orderType": "STOP_MARKET", "triggerPrice": "100"},
            ]

    client = FakeClient()
    connector._client = lambda: _AsyncContext(client)  # type: ignore[method-assign]

    orders = await connector.fetch_open_orders(["BTC"], include_conditional_orders=False)

    assert client.algo_calls == 0
    assert len(orders) == 1
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


@pytest.mark.asyncio
async def test_fetch_candles_resolves_bare_symbol_to_market_symbol():
    connector = _build_connector("binance")

    class FakeClient:
        markets = {
            "BTC/USDT:USDT": {
                "symbol": "BTC/USDT:USDT",
                "base": "BTC",
                "quote": "USDT",
                "swap": True,
                "id": "BTCUSDT",
            }
        }

        def __init__(self) -> None:
            self.calls: list[tuple[str, str, int]] = []

        async def fetch_ohlcv(self, symbol, timeframe=None, limit=None):  # noqa: ANN001
            self.calls.append((symbol, timeframe, limit))
            return [[1710000000000, 100.0, 101.0, 99.0, 100.5, 1234.0]]

    client = FakeClient()
    connector._client = lambda: _AsyncContext(client)  # type: ignore[method-assign]

    candles = await connector.fetch_candles("BTC", "15m", 15)

    assert client.calls == [("BTC/USDT:USDT", "15m", 15)]
    assert len(candles) == 1
    assert candles[0].close == 100.5
