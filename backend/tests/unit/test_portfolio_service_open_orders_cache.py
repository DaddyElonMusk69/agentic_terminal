from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from app.application.portfolio.service import PortfolioService
from app.domain.portfolio.models import ExchangeAccount, ExchangeCredentials


class _RepoStub:
    def __init__(self) -> None:
        now = datetime.now(timezone.utc)
        self.account = ExchangeAccount(
            id="acct-1",
            name="primary",
            exchange="binance",
            is_active=True,
            is_testnet=False,
            created_at=now,
            updated_at=now,
        )
        self.credentials = ExchangeCredentials(
            account_id="acct-1",
            api_key="key",
            api_secret="secret",
        )

    async def get_active_account(self):
        return self.account

    async def get_credentials(self, account_id: str):
        if account_id != self.account.id:
            return None
        return self.credentials


class _ConnectorStub:
    def __init__(self) -> None:
        self.fetch_calls: list[tuple[list[str] | None, bool]] = []
        self.cancel_calls: list[tuple[str, str]] = []
        self.delay_seconds = 0.0

    async def fetch_open_orders(self, symbols=None, *, include_conditional_orders=True):  # noqa: ANN001
        self.fetch_calls.append((list(symbols) if symbols else None, bool(include_conditional_orders)))
        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)
        if symbols:
            return [{"id": "ord-1", "symbol": symbols[0]}]
        return [{"id": "ord-1", "symbol": "BTC/USDT:USDT"}]

    async def cancel_order(self, order_id: str, symbol: str):
        self.cancel_calls.append((order_id, symbol))
        return {"id": order_id, "symbol": symbol, "status": "canceled"}


class _FactoryStub:
    def __init__(self, connector: _ConnectorStub) -> None:
        self._connector = connector

    def create(self, account, credentials):  # noqa: ANN001
        return self._connector


@pytest.mark.asyncio
async def test_get_open_orders_uses_short_cache_for_same_symbol_set():
    repo = _RepoStub()
    connector = _ConnectorStub()
    service = PortfolioService(repo, _FactoryStub(connector))

    first = await service.get_open_orders(["eth", "BTC"])
    second = await service.get_open_orders(["BTC", "ETH"])

    assert first == second
    assert connector.fetch_calls == [(["BTC", "ETH"], True)]


@pytest.mark.asyncio
async def test_get_open_orders_single_flight_collapses_concurrent_requests():
    repo = _RepoStub()
    connector = _ConnectorStub()
    connector.delay_seconds = 0.03
    service = PortfolioService(repo, _FactoryStub(connector))

    await asyncio.gather(
        service.get_open_orders(["BTC"]),
        service.get_open_orders(["BTC"]),
    )

    assert connector.fetch_calls == [(["BTC"], True)]


@pytest.mark.asyncio
async def test_cancel_order_invalidates_open_orders_cache():
    repo = _RepoStub()
    connector = _ConnectorStub()
    service = PortfolioService(repo, _FactoryStub(connector))

    await service.get_open_orders(["BTC"])
    await service.cancel_order("ord-1", "BTC")
    await service.get_open_orders(["BTC"])

    assert connector.cancel_calls == [("ord-1", "BTC")]
    assert connector.fetch_calls == [(["BTC"], True), (["BTC"], True)]


@pytest.mark.asyncio
async def test_get_open_orders_caches_conditional_and_non_conditional_separately():
    repo = _RepoStub()
    connector = _ConnectorStub()
    service = PortfolioService(repo, _FactoryStub(connector))

    await service.get_open_orders(["BTC"], include_conditional_orders=False)
    await service.get_open_orders(["BTC"], include_conditional_orders=False)
    await service.get_open_orders(["BTC"], include_conditional_orders=True)

    assert connector.fetch_calls == [
        (["BTC"], False),
        (["BTC"], True),
    ]
