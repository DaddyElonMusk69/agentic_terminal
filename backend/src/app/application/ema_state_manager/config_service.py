from app.domain.ema_state_manager.interfaces import EmaStateManagerConfigRepository
from app.domain.ema_state_manager.models import (
    DEFAULT_EMA_STATE_MANAGER_CONFIG,
    EmaStateManagerConfig,
)


class EmaStateManagerConfigService:
    def __init__(self, repository: EmaStateManagerConfigRepository) -> None:
        self._repository = repository

    async def get_config(self) -> EmaStateManagerConfig:
        config = await self._repository.get_config()
        return config or DEFAULT_EMA_STATE_MANAGER_CONFIG

    async def update_config(
        self,
        min_resonance: int,
        ema_resonance_cooldown_seconds: int,
        bb_rejection_cooldown_seconds: int,
        bb_exit_warning_cooldown_seconds: int,
        position_check_interval_seconds: int,
        bb_rejection_min_touches: int,
        bb_htf_min_interval_minutes: int,
        emit_new_resonance: bool,
        emit_resonance_increase: bool,
        emit_structure_shift: bool,
        emit_resonance_refresh: bool,
        emit_bb_rejection_upper: bool,
        emit_bb_rejection_lower: bool,
        emit_position_management: bool,
        emit_bb_exit_warning: bool,
    ) -> EmaStateManagerConfig:
        config = EmaStateManagerConfig(
            min_resonance=min_resonance,
            ema_resonance_cooldown_seconds=ema_resonance_cooldown_seconds,
            bb_rejection_cooldown_seconds=bb_rejection_cooldown_seconds,
            bb_exit_warning_cooldown_seconds=bb_exit_warning_cooldown_seconds,
            position_check_interval_seconds=position_check_interval_seconds,
            bb_rejection_min_touches=bb_rejection_min_touches,
            bb_htf_min_interval_minutes=bb_htf_min_interval_minutes,
            emit_new_resonance=emit_new_resonance,
            emit_resonance_increase=emit_resonance_increase,
            emit_structure_shift=emit_structure_shift,
            emit_resonance_refresh=emit_resonance_refresh,
            emit_bb_rejection_upper=emit_bb_rejection_upper,
            emit_bb_rejection_lower=emit_bb_rejection_lower,
            emit_position_management=emit_position_management,
            emit_bb_exit_warning=emit_bb_exit_warning,
        )
        return await self._repository.upsert(config)
