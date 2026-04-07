from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from app.application.portfolio.service import PortfolioService
from app.domain.portfolio.models import DailyPnlSnapshot, ExchangeAccount, ExchangeCredentials


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
        self.daily_pnl_calls = 0
        self.delay_seconds = 0.0

    async def fetch_daily_pnl(self):
        self.daily_pnl_calls += 1
        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)
        return DailyPnlSnapshot(
            realized_pnl=12.34,
            trade_count=2,
            fills=[],
            exchange=None,
        )


class _FactoryStub:
    def __init__(self, connector: _ConnectorStub) -> None:
        self._connector = connector

    def create(self, account, credentials):  # noqa: ANN001
        return self._connector


@pytest.mark.asyncio
async def test_get_daily_pnl_uses_short_cache_for_repeated_calls():
    repo = _RepoStub()
    connector = _ConnectorStub()
    service = PortfolioService(repo, _FactoryStub(connector))

    first = await service.get_daily_pnl()
    second = await service.get_daily_pnl()

    assert first == second
    assert first.exchange == "binance"
    assert connector.daily_pnl_calls == 1


@pytest.mark.asyncio
async def test_get_daily_pnl_single_flight_collapses_concurrent_requests():
    repo = _RepoStub()
    connector = _ConnectorStub()
    connector.delay_seconds = 0.03
    service = PortfolioService(repo, _FactoryStub(connector))

    first, second = await asyncio.gather(
        service.get_daily_pnl(),
        service.get_daily_pnl(),
    )

    assert first == second
    assert connector.daily_pnl_calls == 1
