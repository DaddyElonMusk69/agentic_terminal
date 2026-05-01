import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.infrastructure.repositories.ema_scanner_repository import SqlEmaScannerRepository


@pytest.mark.asyncio
async def test_ema_scanner_repository_falls_back_when_scan_interval_column_missing():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE ema_scanner_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tolerance_pct FLOAT NOT NULL,
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                INSERT INTO ema_scanner_config (tolerance_pct, created_at, updated_at)
                VALUES (0.2, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE TABLE monitored_intervals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    interval VARCHAR(10) NOT NULL,
                    display_order INTEGER NOT NULL,
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                INSERT INTO monitored_intervals (interval, display_order, created_at, updated_at)
                VALUES ('1h', 1, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')
                """
            )
        )

    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    repository = SqlEmaScannerRepository(sessionmaker)

    assert await repository.get_tolerance() == 0.2
    assert await repository.get_scan_intervals() is None
    assert await repository.set_scan_intervals(["1h"]) is None
    assert await repository.list_monitored_intervals() == ["1h"]

    await engine.dispose()


@pytest.mark.asyncio
async def test_ema_scanner_repository_rechecks_after_column_is_added():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE ema_scanner_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tolerance_pct FLOAT NOT NULL,
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                INSERT INTO ema_scanner_config (tolerance_pct, created_at, updated_at)
                VALUES (0.2, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE TABLE monitored_intervals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    interval VARCHAR(10) NOT NULL,
                    display_order INTEGER NOT NULL,
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                INSERT INTO monitored_intervals (interval, display_order, created_at, updated_at)
                VALUES ('1h', 1, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')
                """
            )
        )

    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    repository = SqlEmaScannerRepository(sessionmaker)

    assert await repository.get_scan_intervals() is None

    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE ema_scanner_config ADD COLUMN scan_intervals TEXT"))

    assert await repository.set_scan_intervals(["1h"]) == ["1h"]
    assert await repository.get_scan_intervals() == ["1h"]

    await engine.dispose()
