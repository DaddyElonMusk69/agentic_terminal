from functools import lru_cache

from app.application.ema_scanner.service import EmaScannerService
from app.application.ema_scanner.runner import EmaScanRunner
from app.application.ema_state_manager.dependencies import get_ema_state_manager_service
from app.application.ema_scanner.config_service import EmaScannerConfigService
from app.application.monitored_assets.dependencies import get_monitored_assets_service
from app.application.portfolio.dependencies import get_portfolio_service
from app.application.scanner_results.dependencies import get_scanner_results_service
from app.infrastructure.db import get_sessionmaker
from app.infrastructure.external.binance_client import BinanceClient
from app.infrastructure.repositories.ema_scanner_repository import SqlEmaScannerRepository


@lru_cache(maxsize=1)
def get_ema_scanner_service() -> EmaScannerService:
    return EmaScannerService(get_portfolio_service(), BinanceClient())


@lru_cache(maxsize=1)
def get_ema_config_service() -> EmaScannerConfigService:
    repository = SqlEmaScannerRepository(get_sessionmaker())
    return EmaScannerConfigService(repository, get_monitored_assets_service())


@lru_cache(maxsize=1)
def get_ema_scan_runner() -> EmaScanRunner:
    return EmaScanRunner(
        config_service=get_ema_config_service(),
        scanner_service=get_ema_scanner_service(),
        results_service=get_scanner_results_service(),
        state_service=get_ema_state_manager_service(),
        portfolio_service=get_portfolio_service(),
    )
