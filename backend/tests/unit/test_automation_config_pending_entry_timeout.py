import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.application.automation.config_service import AutomationConfigService
from app.infrastructure.db.models import Base
from app.infrastructure.repositories.automation_config_repository import SqlAutomationConfigRepository


@pytest.mark.asyncio
async def test_pending_entry_timeout_round_trip_in_automation_config():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    repository = SqlAutomationConfigRepository(sessionmaker)
    service = AutomationConfigService(repository)

    default_config = await service.get_config()
    assert default_config.pending_entry_timeout_seconds == 900

    updated = await service.update_config(
        execution_mode="dry_run",
        ema_interval_seconds=60,
        quant_interval_seconds=60,
        pending_entry_timeout_seconds=1800,
        provider="openai",
        model="gpt-5",
        reasoning_effort=None,
        include_entry_timing_15m_chart=False,
        use_all_monitored_interval_charts=False,
        reverse_order_enabled=False,
        vegas_prompt_configs=None,
    )
    assert updated.pending_entry_timeout_seconds == 1800

    reloaded = await service.get_config()
    assert reloaded.pending_entry_timeout_seconds == 1800
