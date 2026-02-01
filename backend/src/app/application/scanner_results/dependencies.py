from functools import lru_cache

from app.application.scanner_results.service import ScannerResultsService
from app.infrastructure.db import get_sessionmaker
from app.infrastructure.repositories.scanner_results_repository import SqlScannerResultsRepository


@lru_cache(maxsize=1)
def get_scanner_results_service() -> ScannerResultsService:
    repository = SqlScannerResultsRepository(get_sessionmaker())
    return ScannerResultsService(repository)
