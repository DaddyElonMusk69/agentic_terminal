from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.ema_state_manager.interfaces import EmaStateManagerConfigRepository
from app.domain.ema_state_manager.models import EmaStateManagerConfig
from app.infrastructure.db.models.ema_state_manager import EmaStateManagerConfigModel


class SqlEmaStateManagerRepository(EmaStateManagerConfigRepository):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def get_config(self) -> Optional[EmaStateManagerConfig]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(EmaStateManagerConfigModel).order_by(EmaStateManagerConfigModel.id)
            )
            model = result.scalars().first()
            if model is None:
                return None
            return EmaStateManagerConfig(
                min_resonance=model.min_resonance,
                ema_resonance_cooldown_seconds=model.ema_resonance_cooldown_seconds,
                bb_rejection_cooldown_seconds=model.bb_rejection_cooldown_seconds,
                bb_exit_warning_cooldown_seconds=model.bb_exit_warning_cooldown_seconds,
                position_check_interval_seconds=model.position_check_interval_seconds,
                bb_rejection_min_touches=model.bb_rejection_min_touches,
                bb_htf_min_interval_minutes=model.bb_htf_min_interval_minutes,
                new_resonance_min_touches=(
                    model.new_resonance_min_touches if model.new_resonance_min_touches is not None else 1
                ),
                emit_new_resonance=(
                    model.emit_new_resonance if model.emit_new_resonance is not None else True
                ),
                emit_resonance_increase=(
                    model.emit_resonance_increase if model.emit_resonance_increase is not None else True
                ),
                emit_structure_shift=(
                    model.emit_structure_shift if model.emit_structure_shift is not None else True
                ),
                emit_resonance_refresh=(
                    model.emit_resonance_refresh if model.emit_resonance_refresh is not None else True
                ),
                emit_bb_rejection_upper=(
                    model.emit_bb_rejection_upper if model.emit_bb_rejection_upper is not None else True
                ),
                emit_bb_rejection_lower=(
                    model.emit_bb_rejection_lower if model.emit_bb_rejection_lower is not None else True
                ),
                emit_position_management=(
                    model.emit_position_management if model.emit_position_management is not None else True
                ),
                emit_bb_exit_warning=(
                    model.emit_bb_exit_warning if model.emit_bb_exit_warning is not None else True
                ),
            )

    async def upsert(self, config: EmaStateManagerConfig) -> EmaStateManagerConfig:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(EmaStateManagerConfigModel).order_by(EmaStateManagerConfigModel.id).limit(1)
            )
            model = result.scalars().first()
            if model is None:
                model = EmaStateManagerConfigModel(
                    min_resonance=config.min_resonance,
                    ema_resonance_cooldown_seconds=config.ema_resonance_cooldown_seconds,
                    bb_rejection_cooldown_seconds=config.bb_rejection_cooldown_seconds,
                    bb_exit_warning_cooldown_seconds=config.bb_exit_warning_cooldown_seconds,
                    position_check_interval_seconds=config.position_check_interval_seconds,
                    bb_rejection_min_touches=config.bb_rejection_min_touches,
                    bb_htf_min_interval_minutes=config.bb_htf_min_interval_minutes,
                    new_resonance_min_touches=config.new_resonance_min_touches,
                    emit_new_resonance=config.emit_new_resonance,
                    emit_resonance_increase=config.emit_resonance_increase,
                    emit_structure_shift=config.emit_structure_shift,
                    emit_resonance_refresh=config.emit_resonance_refresh,
                    emit_bb_rejection_upper=config.emit_bb_rejection_upper,
                    emit_bb_rejection_lower=config.emit_bb_rejection_lower,
                    emit_position_management=config.emit_position_management,
                    emit_bb_exit_warning=config.emit_bb_exit_warning,
                )
                session.add(model)
            else:
                model.min_resonance = config.min_resonance
                model.ema_resonance_cooldown_seconds = config.ema_resonance_cooldown_seconds
                model.bb_rejection_cooldown_seconds = config.bb_rejection_cooldown_seconds
                model.bb_exit_warning_cooldown_seconds = config.bb_exit_warning_cooldown_seconds
                model.position_check_interval_seconds = config.position_check_interval_seconds
                model.bb_rejection_min_touches = config.bb_rejection_min_touches
                model.bb_htf_min_interval_minutes = config.bb_htf_min_interval_minutes
                model.new_resonance_min_touches = config.new_resonance_min_touches
                model.emit_new_resonance = config.emit_new_resonance
                model.emit_resonance_increase = config.emit_resonance_increase
                model.emit_structure_shift = config.emit_structure_shift
                model.emit_resonance_refresh = config.emit_resonance_refresh
                model.emit_bb_rejection_upper = config.emit_bb_rejection_upper
                model.emit_bb_rejection_lower = config.emit_bb_rejection_lower
                model.emit_position_management = config.emit_position_management
                model.emit_bb_exit_warning = config.emit_bb_exit_warning
            await session.commit()
            await session.refresh(model)
            return EmaStateManagerConfig(
                min_resonance=model.min_resonance,
                ema_resonance_cooldown_seconds=model.ema_resonance_cooldown_seconds,
                bb_rejection_cooldown_seconds=model.bb_rejection_cooldown_seconds,
                bb_exit_warning_cooldown_seconds=model.bb_exit_warning_cooldown_seconds,
                position_check_interval_seconds=model.position_check_interval_seconds,
                bb_rejection_min_touches=model.bb_rejection_min_touches,
                bb_htf_min_interval_minutes=model.bb_htf_min_interval_minutes,
                new_resonance_min_touches=model.new_resonance_min_touches,
                emit_new_resonance=model.emit_new_resonance,
                emit_resonance_increase=model.emit_resonance_increase,
                emit_structure_shift=model.emit_structure_shift,
                emit_resonance_refresh=model.emit_resonance_refresh,
                emit_bb_rejection_upper=model.emit_bb_rejection_upper,
                emit_bb_rejection_lower=model.emit_bb_rejection_lower,
                emit_position_management=model.emit_position_management,
                emit_bb_exit_warning=model.emit_bb_exit_warning,
            )
