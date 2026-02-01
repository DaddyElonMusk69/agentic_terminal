from __future__ import annotations

from functools import lru_cache

from app.application.portfolio.dependencies import get_portfolio_service
from app.application.risk_management.config_service import RiskManagementConfigService
from app.application.risk_management.service import RiskManagementService
from app.infrastructure.db import get_sessionmaker
from app.infrastructure.repositories.risk_management_repository import SqlRiskManagementConfigRepository


@lru_cache(maxsize=1)
def get_risk_management_config_service() -> RiskManagementConfigService:
    repository = SqlRiskManagementConfigRepository(get_sessionmaker())
    return RiskManagementConfigService(repository)


@lru_cache(maxsize=1)
def get_risk_management_service() -> RiskManagementService:
    return RiskManagementService(
        get_risk_management_config_service(),
        get_portfolio_service(),
    )
