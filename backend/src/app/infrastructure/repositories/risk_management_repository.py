from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.risk_management.interfaces import RiskManagementConfigRepository
from app.domain.risk_management.models import RiskManagementConfig
from app.infrastructure.db.models.risk_management import RiskManagementConfigModel


class SqlRiskManagementConfigRepository(RiskManagementConfigRepository):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def get_config(self) -> Optional[RiskManagementConfig]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(RiskManagementConfigModel)
                .order_by(RiskManagementConfigModel.id.desc())
                .limit(1)
            )
            model = result.scalars().first()
            if model is None:
                return None
            return self._to_config(model)

    async def upsert(self, config: RiskManagementConfig) -> RiskManagementConfig:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(RiskManagementConfigModel)
                .order_by(RiskManagementConfigModel.id.desc())
                .limit(1)
            )
            model = result.scalars().first()
            if model is None:
                model = RiskManagementConfigModel()
                session.add(model)

            model.final_goal_usd = config.final_goal_usd
            model.exposure_pct = config.exposure_pct
            model.goal_deadline = config.goal_deadline

            await session.commit()
            await session.refresh(model)
            return self._to_config(model)

    def _to_config(self, model: RiskManagementConfigModel) -> RiskManagementConfig:
        return RiskManagementConfig(
            final_goal_usd=model.final_goal_usd,
            exposure_pct=model.exposure_pct,
            goal_deadline=model.goal_deadline,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
