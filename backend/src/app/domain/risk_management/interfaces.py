from __future__ import annotations

from typing import Optional, Protocol

from app.domain.risk_management.models import RiskManagementConfig


class RiskManagementConfigRepository(Protocol):
    async def get_config(self) -> Optional[RiskManagementConfig]:
        ...

    async def upsert(self, config: RiskManagementConfig) -> RiskManagementConfig:
        ...
