import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.application.ema_scanner.config_service import EmaScannerConfigService
from app.infrastructure.repositories.ema_scanner_repository import SqlEmaScannerRepository
from app.settings import get_settings


class StubAssetsService:
    async def list_assets(self, include_positions: bool = True, force_refresh: bool = False):
        del include_positions, force_refresh
        return ["BTC", "ETH", "SOL"]


@pytest.mark.asyncio
async def test_ema_scanner_repository_builds_config(tmp_path):
    db_path = tmp_path / "ema_repo.db"
    os.environ["BACKEND_DATABASE_URL"] = f"sqlite:///{db_path}"
    get_settings.cache_clear()

    backend_root = Path(__file__).resolve().parents[2]
    alembic_cfg = Config(str(backend_root / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_root / "alembic"))

    command.upgrade(alembic_cfg, "head")

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    repository = SqlEmaScannerRepository(sessionmaker)
    service = EmaScannerConfigService(repository, StubAssetsService())
    config = await service.build_config()

    assert config.tolerance_pct == 0.2
    assert config.ema_lengths == [144, 169]
    assert config.assets == ["BTC", "ETH", "SOL"]
    assert config.timeframes == ["2h", "4h"]

    updated = await service.update_scan_intervals(["4h"])
    assert updated == ["4h"]

    filtered_config = await service.build_config()
    assert filtered_config.timeframes == ["4h"]

    await engine.dispose()
