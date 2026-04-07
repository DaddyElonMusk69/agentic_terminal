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
    assert default_config.max_positions == 3
    assert default_config.auto_add_enabled is False
    assert default_config.auto_add_trigger_atr_multiple == 1.0
    assert default_config.auto_add_tranche_margin_pct == 0.80
    assert default_config.auto_add_max_tranches == 3
    assert default_config.auto_add_protected_stop_roe == 0.002

    updated = await service.update_config(
        execution_mode="dry_run",
        ema_interval_seconds=60,
        quant_interval_seconds=60,
        pending_entry_timeout_seconds=1800,
        max_positions=5,
        provider="openai",
        model="gpt-5",
        auto_add_enabled=True,
        auto_add_trigger_atr_multiple=1.25,
        auto_add_tranche_margin_pct=0.65,
        auto_add_max_tranches=4,
        auto_add_protected_stop_roe=0.004,
        reasoning_effort=None,
        include_entry_timing_15m_chart=False,
        use_all_monitored_interval_charts=False,
        reverse_order_enabled=False,
        vegas_prompt_configs=None,
    )
    assert updated.pending_entry_timeout_seconds == 1800
    assert updated.max_positions == 5
    assert updated.auto_add_enabled is True
    assert updated.auto_add_trigger_atr_multiple == 1.25
    assert updated.auto_add_tranche_margin_pct == 0.65
    assert updated.auto_add_max_tranches == 4
    assert updated.auto_add_protected_stop_roe == 0.004

    reloaded = await service.get_config()
    assert reloaded.pending_entry_timeout_seconds == 1800
    assert reloaded.max_positions == 5
    assert reloaded.auto_add_enabled is True
    assert reloaded.auto_add_trigger_atr_multiple == 1.25
    assert reloaded.auto_add_tranche_margin_pct == 0.65
    assert reloaded.auto_add_max_tranches == 4
    assert reloaded.auto_add_protected_stop_roe == 0.004
