from functools import lru_cache

from app.application.dynamic_assets.service import DynamicAssetsService
from app.application.portfolio.dependencies import get_portfolio_service
from app.infrastructure.crypto.cipher import get_credentials_cipher
from app.infrastructure.db import get_sessionmaker
from app.infrastructure.repositories.dynamic_assets_repository import SqlDynamicAssetsConfigRepository


@lru_cache(maxsize=1)
def get_dynamic_assets_service() -> DynamicAssetsService:
    repository = SqlDynamicAssetsConfigRepository(
        get_sessionmaker(),
        cipher=get_credentials_cipher(),
    )
    return DynamicAssetsService(
        repository=repository,
        portfolio_service=get_portfolio_service(),
    )
