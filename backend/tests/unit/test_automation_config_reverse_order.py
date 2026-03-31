import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.application.automation.config_service import AutomationConfigService
from app.infrastructure.db.models import Base
from app.infrastructure.repositories.automation_config_repository import SqlAutomationConfigRepository


@pytest.mark.asyncio
async def test_reverse_order_enabled_round_trip_in_automation_config():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    repository = SqlAutomationConfigRepository(sessionmaker)
    service = AutomationConfigService(repository)

    default_config = await service.get_config()
    assert default_config.reverse_order_enabled is False

    updated_true = await service.update_config(
        execution_mode="dry_run",
        ema_interval_seconds=60,
        quant_interval_seconds=60,
        pending_entry_timeout_seconds=900,
        provider="openai",
        model="gpt-5",
        include_entry_timing_15m_chart=False,
        reverse_order_enabled=True,
        vegas_prompt_configs=None,
    )
    assert updated_true.reverse_order_enabled is True

    reloaded_true = await service.get_config()
    assert reloaded_true.reverse_order_enabled is True

    updated_false = await service.update_config(
        execution_mode="dry_run",
        ema_interval_seconds=60,
        quant_interval_seconds=60,
        pending_entry_timeout_seconds=900,
        provider="openai",
        model="gpt-5",
        include_entry_timing_15m_chart=False,
        reverse_order_enabled=False,
        vegas_prompt_configs=None,
    )
    assert updated_false.reverse_order_enabled is False

    reloaded_false = await service.get_config()
    assert reloaded_false.reverse_order_enabled is False
