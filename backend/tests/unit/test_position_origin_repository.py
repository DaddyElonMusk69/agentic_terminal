from datetime import datetime, timezone

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.domain.portfolio.models import ExchangeAccount, ExchangeCredentials
from app.infrastructure.crypto.cipher import PlaintextCipher
from app.infrastructure.db.models import Base
from app.infrastructure.repositories.position_origin_repository import SqlActivePositionOriginRepository
from app.infrastructure.repositories.sql_exchange_repository import SqlExchangeRepository


@pytest.fixture
async def sessionmaker() -> async_sessionmaker:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_foreign_keys(dbapi_connection, connection_record):  # noqa: ANN001
        del connection_record
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.mark.asyncio
async def test_position_origin_repository_upsert_prune_and_delete(sessionmaker):
    exchange_repo = SqlExchangeRepository(sessionmaker, cipher=PlaintextCipher())
    repo = SqlActivePositionOriginRepository(sessionmaker)
    now = datetime.now(timezone.utc)

    await exchange_repo.create_account(
        ExchangeAccount(
            id="acc-1",
            name="Primary",
            exchange="binance",
            is_active=True,
            is_testnet=False,
            created_at=now,
            updated_at=now,
        ),
        ExchangeCredentials(
            account_id="acc-1",
            api_key="key",
            api_secret="secret",
            passphrase=None,
        ),
    )

    created = await repo.upsert("acc-1", "BTC", "4h", "fast", 0.01, 0.03)
    assert created.symbol == "BTC"
    assert created.anchor_frame == "4h"
    assert created.active_tunnel == "fast"
    assert created.stop_loss_roe == 0.01
    assert created.take_profit_roe == 0.03

    updated = await repo.upsert("acc-1", "BTC", "2h", "mid", 0.02, 0.04)
    assert updated.anchor_frame == "2h"
    assert updated.active_tunnel == "mid"
    assert updated.stop_loss_roe == 0.02
    assert updated.take_profit_roe == 0.04

    await repo.upsert("acc-1", "ETH", "1h", "fast", None, 0.05)

    rows = await repo.get_many("acc-1", ["BTC", "ETH"])
    row_by_symbol = {row.symbol: row for row in rows}
    assert row_by_symbol["BTC"].anchor_frame == "2h"
    assert row_by_symbol["ETH"].active_tunnel == "fast"
    assert row_by_symbol["BTC"].stop_loss_roe == 0.02
    assert row_by_symbol["ETH"].take_profit_roe == 0.05

    pruned = await repo.prune_missing("acc-1", ["BTC"])
    assert pruned == 1

    remaining = await repo.get_many("acc-1", ["BTC", "ETH"])
    assert [row.symbol for row in remaining] == ["BTC"]

    deleted = await repo.delete("acc-1", "BTC")
    assert deleted is True
    assert await repo.get_many("acc-1", ["BTC"]) == []


@pytest.mark.asyncio
async def test_position_origin_repository_cascades_on_account_delete(sessionmaker):
    exchange_repo = SqlExchangeRepository(sessionmaker, cipher=PlaintextCipher())
    repo = SqlActivePositionOriginRepository(sessionmaker)
    now = datetime.now(timezone.utc)

    await exchange_repo.create_account(
        ExchangeAccount(
            id="acc-1",
            name="Primary",
            exchange="binance",
            is_active=True,
            is_testnet=False,
            created_at=now,
            updated_at=now,
        ),
        ExchangeCredentials(
            account_id="acc-1",
            api_key="key",
            api_secret="secret",
            passphrase=None,
        ),
    )
    await repo.upsert("acc-1", "BTC", "4h", "fast", 0.01, 0.03)

    await exchange_repo.delete_account("acc-1")

    assert await repo.get_many("acc-1", ["BTC"]) == []
