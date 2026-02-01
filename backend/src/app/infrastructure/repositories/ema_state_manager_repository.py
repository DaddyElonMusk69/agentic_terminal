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
            )
