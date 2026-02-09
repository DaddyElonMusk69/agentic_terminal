from functools import lru_cache

from app.application.risk_management.dependencies import get_risk_management_config_service
from app.application.trade_guard.service import TradeGuardService
from app.infrastructure.db import get_sessionmaker
from app.infrastructure.repositories.trade_guard_config_repository import SqlTradeGuardConfigRepository


@lru_cache(maxsize=1)
def get_trade_guard_service() -> TradeGuardService:
    sessionmaker = get_sessionmaker()
    config_repo = SqlTradeGuardConfigRepository(sessionmaker)
    risk_config_service = get_risk_management_config_service()
    return TradeGuardService(config_repo, risk_config_service)
