from datetime import datetime, timezone
from typing import List

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.position_origin.interfaces import ActivePositionOriginRepository
from app.domain.position_origin.models import ActivePositionOriginRecord
from app.infrastructure.db.models.position_origin import ActivePositionOriginModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SqlActivePositionOriginRepository(ActivePositionOriginRepository):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def upsert(
        self,
        account_id: str,
        symbol: str,
        anchor_frame: str | None,
        active_tunnel: str | None,
        stop_loss_roe: float | None,
        take_profit_roe: float | None,
    ) -> ActivePositionOriginRecord:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(ActivePositionOriginModel).where(
                    ActivePositionOriginModel.account_id == account_id,
                    ActivePositionOriginModel.symbol == symbol,
                )
            )
            model = result.scalar_one_or_none()
            now = _utcnow()
            if model is None:
                model = ActivePositionOriginModel(
                    account_id=account_id,
                    symbol=symbol,
                    anchor_frame=anchor_frame,
                    active_tunnel=active_tunnel,
                    stop_loss_roe=stop_loss_roe,
                    take_profit_roe=take_profit_roe,
                    created_at=now,
                    updated_at=now,
                )
                session.add(model)
            else:
                model.anchor_frame = anchor_frame
                model.active_tunnel = active_tunnel
                model.stop_loss_roe = stop_loss_roe
                model.take_profit_roe = take_profit_roe
                model.updated_at = now

            await session.commit()
            await session.refresh(model)
            return _to_record(model)

    async def get_many(
        self,
        account_id: str,
        symbols: list[str],
    ) -> List[ActivePositionOriginRecord]:
        if not symbols:
            return []

        async with self._sessionmaker() as session:
            result = await session.execute(
                select(ActivePositionOriginModel).where(
                    ActivePositionOriginModel.account_id == account_id,
                    ActivePositionOriginModel.symbol.in_(symbols),
                )
            )
            return [_to_record(model) for model in result.scalars().all()]

    async def delete(
        self,
        account_id: str,
        symbol: str,
    ) -> bool:
        async with self._sessionmaker() as session:
            result = await session.execute(
                delete(ActivePositionOriginModel).where(
                    ActivePositionOriginModel.account_id == account_id,
                    ActivePositionOriginModel.symbol == symbol,
                )
            )
            await session.commit()
            return bool(result.rowcount)

    async def prune_missing(
        self,
        account_id: str,
        live_symbols: list[str],
    ) -> int:
        async with self._sessionmaker() as session:
            statement = delete(ActivePositionOriginModel).where(
                ActivePositionOriginModel.account_id == account_id
            )
            if live_symbols:
                statement = statement.where(~ActivePositionOriginModel.symbol.in_(live_symbols))
            result = await session.execute(statement)
            await session.commit()
            return int(result.rowcount or 0)


def _to_record(model: ActivePositionOriginModel) -> ActivePositionOriginRecord:
    return ActivePositionOriginRecord(
        account_id=model.account_id,
        symbol=model.symbol,
        anchor_frame=model.anchor_frame,
        active_tunnel=_normalize_active_tunnel_value(model.active_tunnel),
        stop_loss_roe=model.stop_loss_roe,
        take_profit_roe=model.take_profit_roe,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _normalize_active_tunnel_value(value) -> str | None:
    if isinstance(value, list):
        for item in value:
            normalized = str(item).strip()
            if normalized:
                return normalized
        return None
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
