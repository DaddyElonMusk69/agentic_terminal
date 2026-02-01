from app.domain.quant_scanner.interfaces import QuantScannerConfigRepository
from app.domain.quant_scanner.models import QuantScannerConfig
from app.application.monitored_assets.service import MonitoredAssetsService


class QuantScannerConfigService:
    def __init__(
        self,
        repository: QuantScannerConfigRepository,
        assets_service: MonitoredAssetsService,
    ) -> None:
        self._repository = repository
        self._assets_service = assets_service

    async def build_config(
        self,
        quote_asset: str = "USDT",
    ) -> QuantScannerConfig:
        assets = await self._assets_service.list_assets()
        intervals = await self._repository.list_monitored_intervals()

        return QuantScannerConfig(
            assets=assets,
            timeframes=intervals,
            quote_asset=quote_asset,
        )
