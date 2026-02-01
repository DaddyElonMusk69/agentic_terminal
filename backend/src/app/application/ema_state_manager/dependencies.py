from functools import lru_cache

from app.application.ema_state_manager.config_service import EmaStateManagerConfigService
from app.application.ema_state_manager.service import EmaStateManagerService
from app.domain.ema_state_manager.service import EmaStateManager
from app.infrastructure.db import get_sessionmaker
from app.infrastructure.repositories.ema_state_manager_repository import SqlEmaStateManagerRepository


@lru_cache(maxsize=1)
def get_ema_state_config_service() -> EmaStateManagerConfigService:
    repository = SqlEmaStateManagerRepository(get_sessionmaker())
    return EmaStateManagerConfigService(repository)


@lru_cache(maxsize=1)
def get_ema_state_manager_service() -> EmaStateManagerService:
    return EmaStateManagerService(get_ema_state_config_service(), EmaStateManager())
