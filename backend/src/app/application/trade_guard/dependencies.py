from functools import lru_cache

from app.application.trade_guard.service import TradeGuardService
from app.infrastructure.db import get_sessionmaker
from app.infrastructure.repositories.account_setup_repository import SqlAccountSetupRepository
from app.infrastructure.repositories.trade_guard_config_repository import SqlTradeGuardConfigRepository


@lru_cache(maxsize=1)
def get_trade_guard_service() -> TradeGuardService:
    sessionmaker = get_sessionmaker()
    config_repo = SqlTradeGuardConfigRepository(sessionmaker)
    account_setup_repo = SqlAccountSetupRepository(sessionmaker)
    return TradeGuardService(config_repo, account_setup_repo)
