from datetime import date
from typing import List, Optional, Protocol, Tuple

from app.domain.scanner_results.models import ScannerResultRecord


class ScannerResultsRepository(Protocol):
    async def get_calendar_counts(self) -> List[Tuple[date, int]]:
        ...

    async def list_results_for_date(self, target_date: date) -> List[ScannerResultRecord]:
        ...

    async def get_latest_date(self) -> Optional[date]:
        ...

    async def get_result_by_date_and_ticker(
        self,
        target_date: date,
        ticker: str,
    ) -> Optional[ScannerResultRecord]:
        ...

    async def create_result(
        self,
        target_date: date,
        ticker: str,
        score: int,
        data: dict,
    ) -> ScannerResultRecord:
        ...

    async def update_result(
        self,
        result_id: int,
        score: int,
        data: dict,
    ) -> Optional[ScannerResultRecord]:
        ...

    async def delete_result(self, result_id: int) -> bool:
        ...

    async def list_all_results(self) -> List[ScannerResultRecord]:
        ...
