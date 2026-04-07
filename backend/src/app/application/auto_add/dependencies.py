from functools import lru_cache

from app.application.automation.config_service import AutomationConfigService
from app.application.auto_add.service import AutoAddService
from app.application.portfolio.dependencies import get_portfolio_service
from app.application.trade_executor.dependencies import get_trade_executor_service
from app.application.trade_guard.dependencies import get_trade_guard_service
from app.infrastructure.db import get_sessionmaker
from app.infrastructure.repositories.auto_add_repository import SqlAutoAddRepository
from app.infrastructure.repositories.automation_config_repository import SqlAutomationConfigRepository


@lru_cache(maxsize=1)
def get_auto_add_service() -> AutoAddService:
    repository = SqlAutoAddRepository(get_sessionmaker())
    config_service = AutomationConfigService(SqlAutomationConfigRepository(get_sessionmaker()))
    return AutoAddService(
        repository=repository,
        portfolio_service=get_portfolio_service(),
        trade_guard=get_trade_guard_service(),
        trade_executor=get_trade_executor_service(),
        automation_config_service=config_service,
    )
