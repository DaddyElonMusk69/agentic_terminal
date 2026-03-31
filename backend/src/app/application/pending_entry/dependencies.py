from functools import lru_cache

from app.application.automation.config_service import AutomationConfigService
from app.application.bus.outbox_service import OutboxService
from app.application.pending_entry.service import PendingEntryService
from app.application.portfolio.dependencies import get_portfolio_service
from app.application.position_origin.dependencies import get_position_origin_service
from app.application.trade_executor.dependencies import get_trade_executor_service
from app.infrastructure.bus.outbox_repository import OutboxRepository
from app.infrastructure.db import get_sessionmaker
from app.infrastructure.repositories.automation_config_repository import SqlAutomationConfigRepository
from app.infrastructure.repositories.pending_entry_repository import SqlPendingEntryRepository


@lru_cache(maxsize=1)
def get_pending_entry_service() -> PendingEntryService:
    repository = SqlPendingEntryRepository(get_sessionmaker())
    config_service = AutomationConfigService(SqlAutomationConfigRepository(get_sessionmaker()))
    return PendingEntryService(
        repository=repository,
        portfolio_service=get_portfolio_service(),
        trade_executor=get_trade_executor_service(),
        automation_config_service=config_service,
        position_origin_service=get_position_origin_service(),
        outbox=OutboxService(OutboxRepository(get_sessionmaker())),
    )
