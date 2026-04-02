import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.application.automation.config_service import AutomationConfigService
from app.infrastructure.db.models import Base
from app.infrastructure.repositories.automation_config_repository import SqlAutomationConfigRepository


@pytest.mark.asyncio
async def test_codex_reasoning_effort_round_trip_in_automation_config():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    repository = SqlAutomationConfigRepository(sessionmaker)
    service = AutomationConfigService(repository)

    default_config = await service.get_config()
    assert default_config.reasoning_effort is None

    updated_codex = await service.update_config(
        execution_mode="dry_run",
        ema_interval_seconds=60,
        quant_interval_seconds=60,
        pending_entry_timeout_seconds=900,
        max_positions=3,
        provider="codex",
        model="gpt-5.4",
        reasoning_effort=None,
        include_entry_timing_15m_chart=False,
        use_all_monitored_interval_charts=False,
        reverse_order_enabled=False,
        vegas_prompt_configs=None,
    )
    assert updated_codex.reasoning_effort == "medium"

    reloaded_codex = await service.get_config()
    assert reloaded_codex.reasoning_effort == "medium"

    updated_openai = await service.update_config(
        execution_mode="dry_run",
        ema_interval_seconds=60,
        quant_interval_seconds=60,
        pending_entry_timeout_seconds=900,
        max_positions=3,
        provider="openai",
        model="gpt-5",
        reasoning_effort="high",
        include_entry_timing_15m_chart=False,
        use_all_monitored_interval_charts=False,
        reverse_order_enabled=False,
        vegas_prompt_configs=None,
    )
    assert updated_openai.reasoning_effort == "high"

    reloaded_openai = await service.get_config()
    assert reloaded_openai.reasoning_effort == "high"
