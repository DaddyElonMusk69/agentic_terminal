from functools import lru_cache

from app.application.automation.dependencies import get_outbox_service
from app.application.portfolio.dependencies import get_portfolio_service
from app.application.position_origin.dependencies import get_position_origin_service
from app.application.protection_reconciler.service import ProtectionReconcilerService
from app.application.trade_executor.dependencies import get_trade_executor_service


@lru_cache(maxsize=1)
def get_protection_reconciler_service() -> ProtectionReconcilerService:
    return ProtectionReconcilerService(
        position_origin_service=get_position_origin_service(),
        portfolio_service=get_portfolio_service(),
        trade_executor=get_trade_executor_service(),
        outbox=get_outbox_service(),
    )
