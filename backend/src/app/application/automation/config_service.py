from __future__ import annotations

from dataclasses import replace
from typing import Optional

from app.application.automation.execution_mode import normalize_execution_mode
from app.domain.automation.interfaces import AutomationConfigRepository
from app.domain.automation.models import AutomationConfig


MIN_INTERVAL_SECONDS = 5
MAX_INTERVAL_SECONDS = 3600
DEFAULT_INTERVAL_SECONDS = 60


class AutomationConfigService:
    def __init__(self, repository: AutomationConfigRepository) -> None:
        self._repository = repository

    async def get_config(self) -> AutomationConfig:
        config = await self._repository.get_config()
        if config is None:
            config = await self._repository.upsert(self._default_config())
        return self._normalize_config(config)

    async def update_config(
        self,
        execution_mode: str,
        ema_interval_seconds: int,
        quant_interval_seconds: int,
        provider: Optional[str],
        model: Optional[str],
        include_entry_timing_15m_chart: bool = False,
        vegas_prompt_configs: Optional[dict[str, int]] = None,
    ) -> AutomationConfig:
        normalized = AutomationConfig(
            execution_mode=execution_mode,
            ema_interval_seconds=ema_interval_seconds,
            quant_interval_seconds=quant_interval_seconds,
            provider=provider,
            model=model,
            include_entry_timing_15m_chart=include_entry_timing_15m_chart,
            vegas_prompt_configs=vegas_prompt_configs,
        )
        normalized = self._normalize_config(normalized)
        return await self._repository.upsert(normalized)

    def _default_config(self) -> AutomationConfig:
        return AutomationConfig(
            execution_mode="dry_run",
            ema_interval_seconds=DEFAULT_INTERVAL_SECONDS,
            quant_interval_seconds=DEFAULT_INTERVAL_SECONDS,
            provider=None,
            model=None,
            include_entry_timing_15m_chart=False,
            vegas_prompt_configs=None,
        )

    def _normalize_config(self, config: AutomationConfig) -> AutomationConfig:
        mode = normalize_execution_mode(config.execution_mode).value
        provider = config.provider.strip() if config.provider else None
        model = config.model.strip() if config.model else None
        ema_interval = _normalize_interval(config.ema_interval_seconds, DEFAULT_INTERVAL_SECONDS)
        quant_interval = _normalize_interval(config.quant_interval_seconds, DEFAULT_INTERVAL_SECONDS)
        include_entry_timing_15m_chart = _normalize_bool(config.include_entry_timing_15m_chart)
        prompt_map = _normalize_prompt_map(config.vegas_prompt_configs)
        return replace(
            config,
            execution_mode=mode,
            ema_interval_seconds=ema_interval,
            quant_interval_seconds=quant_interval,
            provider=provider or None,
            model=model or None,
            include_entry_timing_15m_chart=include_entry_timing_15m_chart,
            vegas_prompt_configs=prompt_map,
        )


def _normalize_interval(value: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed < MIN_INTERVAL_SECONDS:
        return MIN_INTERVAL_SECONDS
    if parsed > MAX_INTERVAL_SECONDS:
        return MAX_INTERVAL_SECONDS
    return parsed


def _normalize_prompt_map(values: Optional[dict[str, int]]) -> Optional[dict[str, int]]:
    if not values:
        return None
    cleaned: dict[str, int] = {}
    for key, value in values.items():
        if not key:
            continue
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            cleaned[str(key)] = parsed
    return cleaned or None


def _normalize_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False
