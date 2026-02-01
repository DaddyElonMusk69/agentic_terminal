from functools import lru_cache

from app.application.dynamic_assets.dependencies import get_dynamic_assets_service
from app.application.quant_scanner.config_service import QuantScannerConfigService
from app.application.quant_scanner.netflow_service import NetflowService
from app.application.quant_scanner.runner import QuantScanRunner
from app.application.quant_scanner.service import QuantDataCache, QuantScannerService
from app.application.monitored_assets.dependencies import get_monitored_assets_service
from app.infrastructure.db import get_sessionmaker
from app.infrastructure.external.binance_client import BinanceClient
from app.infrastructure.repositories.quant_scanner_repository import SqlQuantScannerRepository


@lru_cache(maxsize=1)
def get_quant_config_service() -> QuantScannerConfigService:
    repository = SqlQuantScannerRepository(get_sessionmaker())
    return QuantScannerConfigService(repository, get_monitored_assets_service())


@lru_cache(maxsize=1)
def get_quant_scanner_service() -> QuantScannerService:
    dynamic_assets = get_dynamic_assets_service()

    async def _resolve_nofxos_key() -> str | None:
        config = await dynamic_assets.get_config()
        return config.api_key

    netflow_service = NetflowService(api_key_provider=_resolve_nofxos_key)
    return QuantScannerService(
        cache=QuantDataCache(),
        netflow_service=netflow_service,
        binance_client=BinanceClient(),
    )


@lru_cache(maxsize=1)
def get_quant_scan_runner() -> QuantScanRunner:
    return QuantScanRunner(
        config_service=get_quant_config_service(),
        scanner_service=get_quant_scanner_service(),
    )
