from datetime import date, datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.scanner_results.interfaces import ScannerResultsRepository
from app.domain.scanner_results.models import ScannerResultRecord
from app.infrastructure.db.models.scanner_results import ScanResultModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SqlScannerResultsRepository(ScannerResultsRepository):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def get_calendar_counts(self) -> List[Tuple[date, int]]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(ScanResultModel.date, func.count(ScanResultModel.id)).group_by(
                    ScanResultModel.date
                )
            )
            return [(row[0], int(row[1])) for row in result.all()]

    async def list_results_for_date(self, target_date: date) -> List[ScannerResultRecord]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(ScanResultModel)
                .where(ScanResultModel.date == target_date)
                .order_by(ScanResultModel.score.desc())
            )
            return [_to_record(model) for model in result.scalars().all()]

    async def get_latest_date(self) -> Optional[date]:
        async with self._sessionmaker() as session:
            result = await session.execute(select(func.max(ScanResultModel.date)))
            return result.scalar_one_or_none()

    async def get_result_by_date_and_ticker(
        self,
        target_date: date,
        ticker: str,
    ) -> Optional[ScannerResultRecord]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(ScanResultModel).where(
                    ScanResultModel.date == target_date,
                    ScanResultModel.ticker == ticker,
                )
            )
            model = result.scalars().first()
            return _to_record(model) if model else None

    async def create_result(
        self,
        target_date: date,
        ticker: str,
        score: int,
        data: dict,
    ) -> ScannerResultRecord:
        async with self._sessionmaker() as session:
            model = ScanResultModel(
                date=target_date,
                ticker=ticker,
                score=score,
                data=data,
                created_at=_utcnow(),
            )
            session.add(model)
            await session.commit()
            await session.refresh(model)
            return _to_record(model)

    async def update_result(
        self,
        result_id: int,
        score: int,
        data: dict,
    ) -> Optional[ScannerResultRecord]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(ScanResultModel).where(ScanResultModel.id == result_id)
            )
            model = result.scalars().first()
            if model is None:
                return None
            model.score = score
            model.data = data
            await session.commit()
            await session.refresh(model)
            return _to_record(model)

    async def delete_result(self, result_id: int) -> bool:
        async with self._sessionmaker() as session:
            result = await session.execute(
                delete(ScanResultModel).where(ScanResultModel.id == result_id)
            )
            await session.commit()
            return result.rowcount > 0

    async def list_all_results(self) -> List[ScannerResultRecord]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(ScanResultModel).order_by(ScanResultModel.date.desc())
            )
            return [_to_record(model) for model in result.scalars().all()]


def _to_record(model: ScanResultModel) -> ScannerResultRecord:
    return ScannerResultRecord(
        id=model.id,
        date=model.date,
        ticker=model.ticker,
        score=model.score,
        data=model.data,
        created_at=model.created_at,
    )
