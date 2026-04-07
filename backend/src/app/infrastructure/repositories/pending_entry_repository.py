from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.pending_entry.interfaces import PendingEntryRepository
from app.domain.pending_entry.models import (
    ACTIVE_PENDING_ENTRY_STATUSES,
    PendingEntryRecord,
    PendingEntrySnapshot,
    PendingEntryStatus,
)
from app.infrastructure.db.models.pending_entry import PendingEntryOrderModel


class SqlPendingEntryRepository(PendingEntryRepository):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def create(self, record: PendingEntryRecord) -> PendingEntryRecord:
        async with self._sessionmaker() as session:
            model = _to_model(record)
            session.add(model)
            await session.commit()
            await session.refresh(model)
            return _to_record(model)

    async def update(self, record: PendingEntryRecord) -> PendingEntryRecord:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(PendingEntryOrderModel).where(PendingEntryOrderModel.id == record.id)
            )
            model = result.scalar_one_or_none()
            if model is None:
                raise KeyError(f"Pending entry {record.id} not found")

            model.account_id = record.account_id
            model.session_id = record.session_id
            model.symbol = record.symbol
            model.exchange_symbol = record.exchange_symbol
            model.side = record.side
            model.exchange_order_id = record.exchange_order_id
            model.limit_price = record.limit_price
            model.intended_size_usd = record.intended_size_usd
            model.intended_quantity = record.intended_quantity
            model.filled_quantity = record.filled_quantity
            model.leverage = record.leverage
            model.time_in_force = record.time_in_force
            model.stop_loss = record.stop_loss
            model.take_profit = record.take_profit
            model.stop_loss_roe = record.stop_loss_roe
            model.take_profit_roe = record.take_profit_roe
            model.anchor_frame = record.anchor_frame
            model.active_tunnel = record.active_tunnel
            model.status = record.status.value
            model.placed_at = record.placed_at
            model.expires_at = record.expires_at
            model.resolved_at = record.resolved_at
            model.last_reconciled_at = record.last_reconciled_at
            model.last_error = record.last_error
            model.order_payload = record.order_payload

            await session.commit()
            await session.refresh(model)
            return _to_record(model)

    async def get(self, entry_id: str) -> Optional[PendingEntryRecord]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(PendingEntryOrderModel).where(PendingEntryOrderModel.id == entry_id)
            )
            model = result.scalar_one_or_none()
            return _to_record(model) if model else None

    async def get_by_exchange_order_id(
        self,
        account_id: str,
        exchange_order_id: str,
    ) -> Optional[PendingEntryRecord]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(PendingEntryOrderModel).where(
                    PendingEntryOrderModel.account_id == account_id,
                    PendingEntryOrderModel.exchange_order_id == exchange_order_id,
                )
            )
            model = result.scalar_one_or_none()
            return _to_record(model) if model else None

    async def list_active(self, account_id: str) -> List[PendingEntryRecord]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(PendingEntryOrderModel)
                .where(
                    PendingEntryOrderModel.account_id == account_id,
                    PendingEntryOrderModel.status.in_(_active_status_values()),
                )
                .order_by(PendingEntryOrderModel.placed_at.asc())
            )
            return [_to_record(model) for model in result.scalars().all()]

    async def list_active_for_symbol(
        self,
        account_id: str,
        symbol: str,
    ) -> List[PendingEntryRecord]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(PendingEntryOrderModel)
                .where(
                    PendingEntryOrderModel.account_id == account_id,
                    PendingEntryOrderModel.symbol == symbol,
                    PendingEntryOrderModel.status.in_(_active_status_values()),
                )
                .order_by(PendingEntryOrderModel.placed_at.asc())
            )
            return [_to_record(model) for model in result.scalars().all()]

    async def list_active_snapshots(self, account_id: str) -> List[PendingEntrySnapshot]:
        rows = await self.list_active(account_id)
        return [
            PendingEntrySnapshot(
                id=row.id,
                symbol=row.symbol,
                side=row.side,
                limit_price=row.limit_price,
                status=row.status,
                placed_at=row.placed_at,
                expires_at=row.expires_at,
                exchange_order_id=row.exchange_order_id,
                filled_quantity=row.filled_quantity,
                intended_quantity=row.intended_quantity,
            )
            for row in rows
        ]


def _active_status_values() -> list[str]:
    return [status.value for status in ACTIVE_PENDING_ENTRY_STATUSES]


def _to_model(record: PendingEntryRecord) -> PendingEntryOrderModel:
    return PendingEntryOrderModel(
        id=record.id,
        account_id=record.account_id,
        session_id=record.session_id,
        symbol=record.symbol,
        exchange_symbol=record.exchange_symbol,
        side=record.side,
        exchange_order_id=record.exchange_order_id,
        limit_price=record.limit_price,
        intended_size_usd=record.intended_size_usd,
        intended_quantity=record.intended_quantity,
        filled_quantity=record.filled_quantity,
        leverage=record.leverage,
        time_in_force=record.time_in_force,
        stop_loss=record.stop_loss,
        take_profit=record.take_profit,
        stop_loss_roe=record.stop_loss_roe,
        take_profit_roe=record.take_profit_roe,
        anchor_frame=record.anchor_frame,
        active_tunnel=record.active_tunnel,
        status=record.status.value,
        placed_at=_ensure_utc(record.placed_at),
        expires_at=_ensure_utc(record.expires_at),
        resolved_at=_ensure_utc(record.resolved_at),
        last_reconciled_at=_ensure_utc(record.last_reconciled_at),
        last_error=record.last_error,
        order_payload=record.order_payload,
    )


def _to_record(model: PendingEntryOrderModel) -> PendingEntryRecord:
    return PendingEntryRecord(
        id=model.id,
        account_id=model.account_id,
        session_id=model.session_id,
        symbol=model.symbol,
        exchange_symbol=model.exchange_symbol,
        side=model.side,
        exchange_order_id=model.exchange_order_id,
        limit_price=model.limit_price,
        intended_size_usd=model.intended_size_usd,
        intended_quantity=model.intended_quantity,
        filled_quantity=model.filled_quantity,
        leverage=model.leverage,
        time_in_force=model.time_in_force,
        stop_loss=model.stop_loss,
        take_profit=model.take_profit,
        stop_loss_roe=model.stop_loss_roe,
        take_profit_roe=model.take_profit_roe,
        anchor_frame=model.anchor_frame,
        active_tunnel=model.active_tunnel,
        status=PendingEntryStatus(str(model.status).upper()),
        placed_at=_ensure_utc(model.placed_at),
        expires_at=_ensure_utc(model.expires_at),
        resolved_at=_ensure_utc(model.resolved_at),
        last_reconciled_at=_ensure_utc(model.last_reconciled_at),
        last_error=model.last_error,
        order_payload=model.order_payload,
        created_at=_ensure_utc(model.created_at),
        updated_at=_ensure_utc(model.updated_at),
    )


def _ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
