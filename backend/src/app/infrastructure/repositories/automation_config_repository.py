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
            model.provider = config.provider
            model.model = config.model
            model.vegas_prompt_configs = config.vegas_prompt_configs or None

            await session.commit()
            await session.refresh(model)
            return self._to_config(model)

    def _to_config(self, model: AutomationConfigModel) -> AutomationConfig:
        return AutomationConfig(
            execution_mode=model.execution_mode,
            ema_interval_seconds=model.ema_interval_seconds,
            quant_interval_seconds=model.quant_interval_seconds,
            provider=model.provider,
            model=model.model,
            vegas_prompt_configs=model.vegas_prompt_configs,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
