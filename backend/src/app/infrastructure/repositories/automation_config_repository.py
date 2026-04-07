from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.automation.interfaces import AutomationConfigRepository
from app.domain.automation.models import AutomationConfig
from app.infrastructure.db.models.automation import AutomationConfigModel


class SqlAutomationConfigRepository(AutomationConfigRepository):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def get_config(self) -> Optional[AutomationConfig]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(AutomationConfigModel)
                .order_by(AutomationConfigModel.id.desc())
                .limit(1)
            )
            model = result.scalars().first()
            if model is None:
                return None
            return self._to_config(model)

    async def upsert(self, config: AutomationConfig) -> AutomationConfig:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(AutomationConfigModel)
                .order_by(AutomationConfigModel.id.desc())
                .limit(1)
            )
            model = result.scalars().first()
            if model is None:
                model = AutomationConfigModel()
                session.add(model)

            model.execution_mode = config.execution_mode
            model.ema_interval_seconds = config.ema_interval_seconds
            model.quant_interval_seconds = config.quant_interval_seconds
            model.pending_entry_timeout_seconds = config.pending_entry_timeout_seconds
            model.max_positions = config.max_positions
            model.auto_add_enabled = bool(config.auto_add_enabled)
            model.auto_add_trigger_atr_multiple = config.auto_add_trigger_atr_multiple
            model.auto_add_tranche_margin_pct = config.auto_add_tranche_margin_pct
            model.auto_add_max_tranches = config.auto_add_max_tranches
            model.auto_add_protected_stop_roe = config.auto_add_protected_stop_roe
            model.provider = config.provider
            model.model = config.model
            model.reasoning_effort = config.reasoning_effort
            model.include_entry_timing_15m_chart = config.include_entry_timing_15m_chart
            model.use_all_monitored_interval_charts = config.use_all_monitored_interval_charts
            model.reverse_order_enabled = config.reverse_order_enabled
            model.vegas_prompt_configs = config.vegas_prompt_configs or None

            await session.commit()
            await session.refresh(model)
            return self._to_config(model)

    def _to_config(self, model: AutomationConfigModel) -> AutomationConfig:
        return AutomationConfig(
            execution_mode=model.execution_mode,
            ema_interval_seconds=model.ema_interval_seconds,
            quant_interval_seconds=model.quant_interval_seconds,
            pending_entry_timeout_seconds=model.pending_entry_timeout_seconds,
            max_positions=model.max_positions,
            provider=model.provider,
            model=model.model,
            auto_add_enabled=bool(model.auto_add_enabled),
            auto_add_trigger_atr_multiple=model.auto_add_trigger_atr_multiple,
            auto_add_tranche_margin_pct=model.auto_add_tranche_margin_pct,
            auto_add_max_tranches=model.auto_add_max_tranches,
            auto_add_protected_stop_roe=model.auto_add_protected_stop_roe,
            reasoning_effort=model.reasoning_effort,
            include_entry_timing_15m_chart=bool(model.include_entry_timing_15m_chart),
            use_all_monitored_interval_charts=bool(model.use_all_monitored_interval_charts),
            reverse_order_enabled=bool(model.reverse_order_enabled),
            vegas_prompt_configs=model.vegas_prompt_configs,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
