from functools import lru_cache

from app.application.dynamic_assets.service import DynamicAssetsService
from app.application.oi_rank.dependencies import get_oi_rank_service
from app.application.portfolio.dependencies import get_portfolio_service
from app.infrastructure.crypto.cipher import get_credentials_cipher
from app.infrastructure.db import get_sessionmaker
from app.infrastructure.repositories.dynamic_assets_repository import SqlDynamicAssetsConfigRepository
from app.infrastructure.external.nofxos_dynamic_assets import NofXOSDynamicAssetsClient
from app.infrastructure.external.oi_rank_dynamic_assets import OiRankDynamicAssetsClient
from app.settings import get_settings


@lru_cache(maxsize=1)
def get_dynamic_assets_service() -> DynamicAssetsService:
    repository = SqlDynamicAssetsConfigRepository(
        get_sessionmaker(),
        cipher=get_credentials_cipher(),
    )
    settings = get_settings()
    nofx_client = NofXOSDynamicAssetsClient()
    oi_client = OiRankDynamicAssetsClient(get_oi_rank_service(), nofx_client=nofx_client)
    return DynamicAssetsService(
        repository=repository,
        portfolio_service=get_portfolio_service(),
        nofx_client=nofx_client,
        oi_rank_client=oi_client,
        default_oi_source=(settings.dynamic_assets_oi_source or "nofx").strip().lower(),
    )
