from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.auto_add.interfaces import AutoAddRepository
from app.domain.auto_add.models import (
    ACTIVE_AUTO_ADD_STATUSES,
    AutoAddPositionRecord,
    AutoAddPositionSnapshot,
    AutoAddStatus,
    AutoAddTrancheKind,
    AutoAddTrancheRecord,
    AutoAddTrancheStatus,
)
from app.infrastructure.db.models.auto_add import AutoAddPositionModel, AutoAddTrancheModel


class SqlAutoAddRepository(AutoAddRepository):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def create_position(self, record: AutoAddPositionRecord) -> AutoAddPositionRecord:
        async with self._sessionmaker() as session:
            model = _to_position_model(record)
            session.add(model)
            await session.commit()
            await session.refresh(model)
            return _to_position_record(model)

    async def update_position(self, record: AutoAddPositionRecord) -> AutoAddPositionRecord:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(AutoAddPositionModel).where(AutoAddPositionModel.id == record.id)
            )
            model = result.scalar_one_or_none()
            if model is None:
                raise KeyError(f"Auto-add position {record.id} not found")
            _apply_position_record(model, record)
            await session.commit()
            await session.refresh(model)
            return _to_position_record(model)

    async def get_position(self, position_id: str) -> AutoAddPositionRecord | None:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(AutoAddPositionModel).where(AutoAddPositionModel.id == position_id)
            )
            model = result.scalar_one_or_none()
            return _to_position_record(model) if model is not None else None

    async def get_active_position_for_symbol(
        self,
        account_id: str,
        symbol: str,
    ) -> AutoAddPositionRecord | None:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(AutoAddPositionModel)
                .where(
                    AutoAddPositionModel.account_id == account_id,
                    AutoAddPositionModel.symbol == symbol,
                    AutoAddPositionModel.active.is_(True),
                )
                .order_by(desc(AutoAddPositionModel.updated_at))
                .limit(1)
            )
            model = result.scalar_one_or_none()
            return _to_position_record(model) if model is not None else None

    async def get_latest_position_for_symbol(
        self,
        account_id: str,
        symbol: str,
    ) -> AutoAddPositionRecord | None:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(AutoAddPositionModel)
                .where(
                    AutoAddPositionModel.account_id == account_id,
                    AutoAddPositionModel.symbol == symbol,
                )
                .order_by(desc(AutoAddPositionModel.updated_at), desc(AutoAddPositionModel.created_at))
                .limit(1)
            )
            model = result.scalar_one_or_none()
            return _to_position_record(model) if model is not None else None

    async def list_active_positions(self, account_id: str) -> list[AutoAddPositionRecord]:
        active_statuses = [status.value for status in ACTIVE_AUTO_ADD_STATUSES]
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(AutoAddPositionModel)
                .where(
                    AutoAddPositionModel.account_id == account_id,
                    AutoAddPositionModel.active.is_(True),
                    AutoAddPositionModel.status.in_(active_statuses),
                )
                .order_by(AutoAddPositionModel.created_at.asc())
            )
            return [_to_position_record(model) for model in result.scalars().all()]

    async def list_latest_positions_for_symbols(
        self,
        account_id: str,
        symbols: list[str],
    ) -> list[AutoAddPositionRecord]:
        if not symbols:
            return []
        unique = sorted({symbol for symbol in symbols if symbol})
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(AutoAddPositionModel)
                .where(
                    AutoAddPositionModel.account_id == account_id,
                    AutoAddPositionModel.symbol.in_(unique),
                )
                .order_by(
                    AutoAddPositionModel.symbol.asc(),
                    desc(AutoAddPositionModel.updated_at),
                    desc(AutoAddPositionModel.created_at),
                )
            )
            latest: dict[str, AutoAddPositionRecord] = {}
            for model in result.scalars().all():
                if model.symbol not in latest:
                    latest[model.symbol] = _to_position_record(model)
            return list(latest.values())

    async def create_tranche(self, record: AutoAddTrancheRecord) -> AutoAddTrancheRecord:
        async with self._sessionmaker() as session:
            model = _to_tranche_model(record)
            session.add(model)
            await session.commit()
            await session.refresh(model)
            return _to_tranche_record(model)

    async def update_tranche(self, record: AutoAddTrancheRecord) -> AutoAddTrancheRecord:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(AutoAddTrancheModel).where(AutoAddTrancheModel.id == record.id)
            )
            model = result.scalar_one_or_none()
            if model is None:
                raise KeyError(f"Auto-add tranche {record.id} not found")
            _apply_tranche_record(model, record)
            await session.commit()
            await session.refresh(model)
            return _to_tranche_record(model)

    async def list_tranches(self, auto_add_position_id: str) -> list[AutoAddTrancheRecord]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(AutoAddTrancheModel)
                .where(AutoAddTrancheModel.auto_add_position_id == auto_add_position_id)
                .order_by(AutoAddTrancheModel.tranche_index.asc(), AutoAddTrancheModel.created_at.asc())
            )
            return [_to_tranche_record(model) for model in result.scalars().all()]

    async def get_snapshot(self, auto_add_position_id: str) -> AutoAddPositionSnapshot | None:
        position = await self.get_position(auto_add_position_id)
        if position is None:
            return None
        tranches = await self.list_tranches(auto_add_position_id)
        return AutoAddPositionSnapshot(record=position, tranches=tuple(tranches))


def _apply_position_record(model: AutoAddPositionModel, record: AutoAddPositionRecord) -> None:
    model.account_id = record.account_id
    model.session_id = record.session_id
    model.symbol = record.symbol
    model.side = record.side
    model.status = record.status.value
    model.initial_margin_used = record.initial_margin_used
    model.initial_stop_price = record.initial_stop_price
    model.original_risk_usd = record.original_risk_usd
    model.trigger_basis_price = record.trigger_basis_price
    model.next_trigger_price = record.next_trigger_price
    model.initial_entry_price = record.initial_entry_price
    model.initial_quantity = record.initial_quantity
    model.expected_quantity = record.expected_quantity
    model.leverage = record.leverage
    model.add_count = record.add_count
    model.max_tranches = record.max_tranches
    model.trigger_atr_multiple = record.trigger_atr_multiple
    model.tranche_margin_pct = record.tranche_margin_pct
    model.protected_stop_roe = record.protected_stop_roe
    model.last_atr_value = record.last_atr_value
    model.last_error = record.last_error
    model.last_capacity_blocked_at = _ensure_utc(record.last_capacity_blocked_at)
    model.last_trade_guard_reason = record.last_trade_guard_reason
    model.last_seen_position_size = record.last_seen_position_size
    model.last_seen_entry_price = record.last_seen_entry_price
    model.last_seen_mark_price = record.last_seen_mark_price
    model.last_seen_margin = record.last_seen_margin
    model.active = record.active
    model.resolved_at = _ensure_utc(record.resolved_at)


def _to_position_model(record: AutoAddPositionRecord) -> AutoAddPositionModel:
    return AutoAddPositionModel(
        id=record.id,
        account_id=record.account_id,
        session_id=record.session_id,
        symbol=record.symbol,
        side=record.side,
        status=record.status.value,
        initial_margin_used=record.initial_margin_used,
        initial_stop_price=record.initial_stop_price,
        original_risk_usd=record.original_risk_usd,
        trigger_basis_price=record.trigger_basis_price,
        next_trigger_price=record.next_trigger_price,
        initial_entry_price=record.initial_entry_price,
        initial_quantity=record.initial_quantity,
        expected_quantity=record.expected_quantity,
        leverage=record.leverage,
        add_count=record.add_count,
        max_tranches=record.max_tranches,
        trigger_atr_multiple=record.trigger_atr_multiple,
        tranche_margin_pct=record.tranche_margin_pct,
        protected_stop_roe=record.protected_stop_roe,
        last_atr_value=record.last_atr_value,
        last_error=record.last_error,
        last_capacity_blocked_at=_ensure_utc(record.last_capacity_blocked_at),
        last_trade_guard_reason=record.last_trade_guard_reason,
        last_seen_position_size=record.last_seen_position_size,
        last_seen_entry_price=record.last_seen_entry_price,
        last_seen_mark_price=record.last_seen_mark_price,
        last_seen_margin=record.last_seen_margin,
        active=record.active,
        resolved_at=_ensure_utc(record.resolved_at),
    )


def _to_position_record(model: AutoAddPositionModel) -> AutoAddPositionRecord:
    return AutoAddPositionRecord(
        id=model.id,
        account_id=model.account_id,
        session_id=model.session_id,
        symbol=model.symbol,
        side=model.side,
        status=AutoAddStatus(str(model.status).upper()),
        initial_margin_used=model.initial_margin_used,
        initial_stop_price=model.initial_stop_price,
        original_risk_usd=model.original_risk_usd,
        trigger_basis_price=model.trigger_basis_price,
        next_trigger_price=model.next_trigger_price,
        initial_entry_price=model.initial_entry_price,
        initial_quantity=model.initial_quantity,
        expected_quantity=model.expected_quantity,
        leverage=model.leverage,
        add_count=model.add_count,
        max_tranches=model.max_tranches,
        trigger_atr_multiple=model.trigger_atr_multiple,
        tranche_margin_pct=model.tranche_margin_pct,
        protected_stop_roe=model.protected_stop_roe,
        last_atr_value=model.last_atr_value,
        last_error=model.last_error,
        last_capacity_blocked_at=_ensure_utc(model.last_capacity_blocked_at),
        last_trade_guard_reason=model.last_trade_guard_reason,
        last_seen_position_size=model.last_seen_position_size,
        last_seen_entry_price=model.last_seen_entry_price,
        last_seen_mark_price=model.last_seen_mark_price,
        last_seen_margin=model.last_seen_margin,
        active=bool(model.active),
        created_at=_ensure_utc(model.created_at),
        updated_at=_ensure_utc(model.updated_at),
        resolved_at=_ensure_utc(model.resolved_at),
    )


def _to_tranche_model(record: AutoAddTrancheRecord) -> AutoAddTrancheModel:
    return AutoAddTrancheModel(
        id=record.id,
        auto_add_position_id=record.auto_add_position_id,
        tranche_index=record.tranche_index,
        kind=record.kind.value,
        status=record.status.value,
        exchange_order_id=record.exchange_order_id,
        trigger_price=record.trigger_price,
        fill_price=record.fill_price,
        filled_quantity=record.filled_quantity,
        margin_used=record.margin_used,
        position_notional_usd=record.position_notional_usd,
        fill_time=_ensure_utc(record.fill_time),
        atr_value=record.atr_value,
        trigger_basis_price=record.trigger_basis_price,
        last_error=record.last_error,
    )


def _to_tranche_record(model: AutoAddTrancheModel) -> AutoAddTrancheRecord:
    return AutoAddTrancheRecord(
        id=model.id,
        auto_add_position_id=model.auto_add_position_id,
        tranche_index=model.tranche_index,
        kind=AutoAddTrancheKind(str(model.kind).upper()),
        status=AutoAddTrancheStatus(str(model.status).upper()),
        exchange_order_id=model.exchange_order_id,
        trigger_price=model.trigger_price,
        fill_price=model.fill_price,
        filled_quantity=model.filled_quantity,
        margin_used=model.margin_used,
        position_notional_usd=model.position_notional_usd,
        fill_time=_ensure_utc(model.fill_time),
        atr_value=model.atr_value,
        trigger_basis_price=model.trigger_basis_price,
        last_error=model.last_error,
        created_at=_ensure_utc(model.created_at),
        updated_at=_ensure_utc(model.updated_at),
    )


def _apply_tranche_record(model: AutoAddTrancheModel, record: AutoAddTrancheRecord) -> None:
    model.auto_add_position_id = record.auto_add_position_id
    model.tranche_index = record.tranche_index
    model.kind = record.kind.value
    model.status = record.status.value
    model.exchange_order_id = record.exchange_order_id
    model.trigger_price = record.trigger_price
    model.fill_price = record.fill_price
    model.filled_quantity = record.filled_quantity
    model.margin_used = record.margin_used
    model.position_notional_usd = record.position_notional_usd
    model.fill_time = _ensure_utc(record.fill_time)
    model.atr_value = record.atr_value
    model.trigger_basis_price = record.trigger_basis_price
    model.last_error = record.last_error


def _ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
