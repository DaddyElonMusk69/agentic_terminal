from functools import lru_cache

from app.application.market_settings.service import MarketSettingsService
from app.infrastructure.db import get_sessionmaker
from app.infrastructure.repositories.market_settings_repository import SqlMarketSettingsRepository


@lru_cache(maxsize=1)
def get_market_settings_service() -> MarketSettingsService:
    repository = SqlMarketSettingsRepository(get_sessionmaker())
    return MarketSettingsService(repository)
