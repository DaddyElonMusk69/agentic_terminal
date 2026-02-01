from functools import lru_cache

from app.application.portfolio.service import PortfolioService
from app.infrastructure.crypto.cipher import get_credentials_cipher
from app.infrastructure.db import get_sessionmaker
from app.infrastructure.exchange.ccxt_connector import CCXTConnectorFactory
from app.infrastructure.repositories.sql_exchange_repository import SqlExchangeRepository


@lru_cache(maxsize=1)
def get_portfolio_service() -> PortfolioService:
    repository = SqlExchangeRepository(get_sessionmaker(), cipher=get_credentials_cipher())
    factory = CCXTConnectorFactory()
    return PortfolioService(repository, factory)
