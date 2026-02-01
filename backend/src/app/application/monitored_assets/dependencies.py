from functools import lru_cache

from app.application.dynamic_assets.dependencies import get_dynamic_assets_service
from app.application.market_settings.dependencies import get_market_settings_service
from app.application.monitored_assets.service import MonitoredAssetsService
from app.infrastructure.db import get_sessionmaker
from app.infrastructure.repositories.monitored_asset_position_repository import (
    MonitoredAssetPositionRepository,
)


@lru_cache(maxsize=1)
def get_monitored_assets_service() -> MonitoredAssetsService:
    return MonitoredAssetsService(
        market_settings=get_market_settings_service(),
        dynamic_assets=get_dynamic_assets_service(),
        position_repository=MonitoredAssetPositionRepository(get_sessionmaker()),
    )
