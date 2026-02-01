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
    ) -> EmaStateManagerConfig:
        config = EmaStateManagerConfig(
            min_resonance=min_resonance,
            ema_resonance_cooldown_seconds=ema_resonance_cooldown_seconds,
            bb_rejection_cooldown_seconds=bb_rejection_cooldown_seconds,
            bb_exit_warning_cooldown_seconds=bb_exit_warning_cooldown_seconds,
            position_check_interval_seconds=position_check_interval_seconds,
            bb_rejection_min_touches=bb_rejection_min_touches,
            bb_htf_min_interval_minutes=bb_htf_min_interval_minutes,
        )
        return await self._repository.upsert(config)
