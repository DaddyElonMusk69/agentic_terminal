from functools import lru_cache

from app.application.oi_rank.service import OiRankService
from app.infrastructure.db import get_sessionmaker
from app.infrastructure.external.binance_client import BinanceClient
from app.infrastructure.repositories.oi_rank_repository import (
    SqlOiRankCacheRepository,
    SqlOiRankConfigRepository,
)


@lru_cache(maxsize=1)
def get_oi_rank_service() -> OiRankService:
    sessionmaker = get_sessionmaker()
    cache_repo = SqlOiRankCacheRepository(sessionmaker)
    config_repo = SqlOiRankConfigRepository(sessionmaker)
    return OiRankService(
        cache_repo=cache_repo,
        config_repo=config_repo,
        binance_client=BinanceClient(),
    )

