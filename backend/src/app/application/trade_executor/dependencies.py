from functools import lru_cache

from app.application.trade_executor.service import TradeExecutorService
from app.infrastructure.crypto.cipher import get_credentials_cipher
from app.infrastructure.db import get_sessionmaker
from app.infrastructure.repositories.sql_exchange_repository import SqlExchangeRepository


@lru_cache(maxsize=1)
def get_trade_executor_service() -> TradeExecutorService:
    repository = SqlExchangeRepository(get_sessionmaker(), cipher=get_credentials_cipher())
    return TradeExecutorService(repository)
