from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.domain.portfolio.models import ExchangeAccount, ExchangeCredentials
from app.infrastructure.crypto.cipher import PlaintextCipher
from app.infrastructure.db.models import Base
from app.infrastructure.repositories.sql_exchange_repository import SqlExchangeRepository


@pytest.fixture
async def sessionmaker() -> async_sessionmaker:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.mark.asyncio
async def test_exchange_repository_crud(sessionmaker):
    repo = SqlExchangeRepository(sessionmaker, cipher=PlaintextCipher())
    now = datetime.now(timezone.utc)

    account = ExchangeAccount(
        id="acc-1",
        name="Primary",
        exchange="binance",
        is_active=False,
        is_testnet=False,
        created_at=now,
        updated_at=now,
    )
    credentials = ExchangeCredentials(
        account_id="acc-1",
        api_key="key",
        api_secret="secret",
        passphrase=None,
    )

    created = await repo.create_account(account, credentials)
    assert created.id == "acc-1"
    assert created.exchange == "binance"
    assert created.is_active is False

    fetched = await repo.get_account("acc-1")
    assert fetched is not None
    assert fetched.name == "Primary"

    creds = await repo.get_credentials("acc-1")
    assert creds is not None
    assert creds.api_key == "key"
    assert creds.api_secret == "secret"


@pytest.mark.asyncio
async def test_exchange_repository_activate(sessionmaker):
    repo = SqlExchangeRepository(sessionmaker, cipher=PlaintextCipher())
    now = datetime.now(timezone.utc)

    account_a = ExchangeAccount(
        id="acc-a",
        name="Alpha",
        exchange="binance",
        is_active=False,
        is_testnet=False,
        created_at=now,
        updated_at=now,
    )
    account_b = ExchangeAccount(
        id="acc-b",
        name="Beta",
        exchange="okx",
        is_active=False,
        is_testnet=True,
        created_at=now,
        updated_at=now,
    )

    await repo.create_account(
        account_a,
        ExchangeCredentials(
            account_id="acc-a",
            api_key="key-a",
            api_secret="secret-a",
            passphrase=None,
        ),
    )
    await repo.create_account(
        account_b,
        ExchangeCredentials(
            account_id="acc-b",
            api_key="key-b",
            api_secret="secret-b",
            passphrase="pass-b",
        ),
    )

    active = await repo.set_active("acc-b")
    assert active.id == "acc-b"
    assert active.is_active is True

    active_account = await repo.get_active_account()
    assert active_account is not None
    assert active_account.id == "acc-b"

    accounts = await repo.list_accounts()
    assert len(accounts) == 2
    assert sum(1 for a in accounts if a.is_active) == 1
