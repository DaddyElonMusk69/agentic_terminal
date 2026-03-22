from functools import lru_cache

from app.application.position_origin.service import PositionOriginService
from app.infrastructure.db import get_sessionmaker
from app.infrastructure.repositories.position_origin_repository import SqlActivePositionOriginRepository


@lru_cache(maxsize=1)
def get_position_origin_service() -> PositionOriginService:
    repository = SqlActivePositionOriginRepository(get_sessionmaker())
    return PositionOriginService(repository)
