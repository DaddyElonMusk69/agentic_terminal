from __future__ import annotations

from datetime import date
from typing import Optional

from app.domain.risk_management.interfaces import RiskManagementConfigRepository
from app.domain.risk_management.models import (
    DEFAULT_RISK_MANAGEMENT_CONFIG,
    RiskManagementConfig,
)


class RiskManagementConfigService:
    def __init__(self, repository: RiskManagementConfigRepository) -> None:
        self._repository = repository

    async def get_config(self) -> RiskManagementConfig:
        config = await self._repository.get_config()
        return config or DEFAULT_RISK_MANAGEMENT_CONFIG

    async def update_config(
        self,
        final_goal_usd: float,
        exposure_pct: float,
        goal_deadline: Optional[date],
    ) -> RiskManagementConfig:
        config = RiskManagementConfig(
            final_goal_usd=final_goal_usd,
            exposure_pct=exposure_pct,
            goal_deadline=goal_deadline,
        )
        return await self._repository.upsert(config)
