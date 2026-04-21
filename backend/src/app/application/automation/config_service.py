from __future__ import annotations

from dataclasses import replace
from typing import Optional

from app.application.automation.execution_mode import normalize_execution_mode
from app.domain.automation.interfaces import AutomationConfigRepository
from app.domain.automation.models import AutomationConfig


MIN_INTERVAL_SECONDS = 5
MAX_INTERVAL_SECONDS = 3600
DEFAULT_INTERVAL_SECONDS = 60
MIN_PENDING_ENTRY_TIMEOUT_SECONDS = 300
MAX_PENDING_ENTRY_TIMEOUT_SECONDS = 7200
DEFAULT_PENDING_ENTRY_TIMEOUT_SECONDS = 900
MIN_MAX_POSITIONS = 1
MAX_MAX_POSITIONS = 10
DEFAULT_MAX_POSITIONS = 3
MIN_AUTO_ADD_TRIGGER_ATR_MULTIPLE = 0.25
MAX_AUTO_ADD_TRIGGER_ATR_MULTIPLE = 3.0
DEFAULT_AUTO_ADD_TRIGGER_ATR_MULTIPLE = 1.0
MIN_AUTO_ADD_TRANCHE_MARGIN_PCT = 0.10
MAX_AUTO_ADD_TRANCHE_MARGIN_PCT = 1.0
DEFAULT_AUTO_ADD_TRANCHE_MARGIN_PCT = 0.80
MIN_AUTO_ADD_MAX_TRANCHES = 1
MAX_AUTO_ADD_MAX_TRANCHES = 5
DEFAULT_AUTO_ADD_MAX_TRANCHES = 3
MIN_AUTO_ADD_PROTECTED_STOP_ROE = 0.0
MAX_AUTO_ADD_PROTECTED_STOP_ROE = 0.02
DEFAULT_AUTO_ADD_PROTECTED_STOP_ROE = 0.002
CODEX_REASONING_EFFORTS = {"minimal", "low", "medium", "high", "xhigh"}
DEFAULT_CODEX_REASONING_EFFORT = "medium"


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
        pending_entry_timeout_seconds: int,
        max_positions: int,
        provider: Optional[str],
        model: Optional[str],
        auto_add_enabled: bool = False,
        auto_add_trigger_atr_multiple: float = DEFAULT_AUTO_ADD_TRIGGER_ATR_MULTIPLE,
        auto_add_tranche_margin_pct: float = DEFAULT_AUTO_ADD_TRANCHE_MARGIN_PCT,
        auto_add_max_tranches: int = DEFAULT_AUTO_ADD_MAX_TRANCHES,
        auto_add_protected_stop_roe: float = DEFAULT_AUTO_ADD_PROTECTED_STOP_ROE,
        reasoning_effort: Optional[str] = None,
        include_entry_timing_15m_chart: bool = False,
        use_all_monitored_interval_charts: bool = False,
        reverse_order_enabled: bool = False,
        vegas_prompt_configs: Optional[dict[str, int]] = None,
    ) -> AutomationConfig:
        normalized = AutomationConfig(
            execution_mode=execution_mode,
            ema_interval_seconds=ema_interval_seconds,
            quant_interval_seconds=quant_interval_seconds,
            pending_entry_timeout_seconds=pending_entry_timeout_seconds,
            max_positions=max_positions,
            provider=provider,
            model=model,
            auto_add_enabled=auto_add_enabled,
            auto_add_trigger_atr_multiple=auto_add_trigger_atr_multiple,
            auto_add_tranche_margin_pct=auto_add_tranche_margin_pct,
            auto_add_max_tranches=auto_add_max_tranches,
            auto_add_protected_stop_roe=auto_add_protected_stop_roe,
            reasoning_effort=reasoning_effort,
            include_entry_timing_15m_chart=include_entry_timing_15m_chart,
            use_all_monitored_interval_charts=use_all_monitored_interval_charts,
            reverse_order_enabled=reverse_order_enabled,
            vegas_prompt_configs=vegas_prompt_configs,
        )
        normalized = self._normalize_config(normalized)
        return await self._repository.upsert(normalized)

    def _default_config(self) -> AutomationConfig:
        return AutomationConfig(
            execution_mode="dry_run",
            ema_interval_seconds=DEFAULT_INTERVAL_SECONDS,
            quant_interval_seconds=DEFAULT_INTERVAL_SECONDS,
            pending_entry_timeout_seconds=DEFAULT_PENDING_ENTRY_TIMEOUT_SECONDS,
            max_positions=DEFAULT_MAX_POSITIONS,
            provider=None,
            model=None,
            auto_add_enabled=False,
            auto_add_trigger_atr_multiple=DEFAULT_AUTO_ADD_TRIGGER_ATR_MULTIPLE,
            auto_add_tranche_margin_pct=DEFAULT_AUTO_ADD_TRANCHE_MARGIN_PCT,
            auto_add_max_tranches=DEFAULT_AUTO_ADD_MAX_TRANCHES,
            auto_add_protected_stop_roe=DEFAULT_AUTO_ADD_PROTECTED_STOP_ROE,
            reasoning_effort=None,
            include_entry_timing_15m_chart=False,
            use_all_monitored_interval_charts=False,
            reverse_order_enabled=False,
            vegas_prompt_configs=None,
        )

    def _normalize_config(self, config: AutomationConfig) -> AutomationConfig:
        mode = normalize_execution_mode(config.execution_mode).value
        provider = config.provider.strip() if config.provider else None
        model = config.model.strip() if config.model else None
        reasoning_effort = _normalize_reasoning_effort(config.reasoning_effort, provider=provider)
        ema_interval = _normalize_interval(config.ema_interval_seconds, DEFAULT_INTERVAL_SECONDS)
        quant_interval = _normalize_interval(config.quant_interval_seconds, DEFAULT_INTERVAL_SECONDS)
        pending_entry_timeout_seconds = _normalize_pending_entry_timeout(
            config.pending_entry_timeout_seconds,
            DEFAULT_PENDING_ENTRY_TIMEOUT_SECONDS,
        )
        max_positions = _normalize_max_positions(
            config.max_positions,
            DEFAULT_MAX_POSITIONS,
        )
        auto_add_enabled = _normalize_bool(config.auto_add_enabled)
        auto_add_trigger_atr_multiple = _normalize_float_range(
            config.auto_add_trigger_atr_multiple,
            DEFAULT_AUTO_ADD_TRIGGER_ATR_MULTIPLE,
            min_value=MIN_AUTO_ADD_TRIGGER_ATR_MULTIPLE,
            max_value=MAX_AUTO_ADD_TRIGGER_ATR_MULTIPLE,
        )
        auto_add_tranche_margin_pct = _normalize_float_range(
            config.auto_add_tranche_margin_pct,
            DEFAULT_AUTO_ADD_TRANCHE_MARGIN_PCT,
            min_value=MIN_AUTO_ADD_TRANCHE_MARGIN_PCT,
            max_value=MAX_AUTO_ADD_TRANCHE_MARGIN_PCT,
        )
        auto_add_max_tranches = _normalize_int_range(
            config.auto_add_max_tranches,
            DEFAULT_AUTO_ADD_MAX_TRANCHES,
            min_value=MIN_AUTO_ADD_MAX_TRANCHES,
            max_value=MAX_AUTO_ADD_MAX_TRANCHES,
        )
        auto_add_protected_stop_roe = _normalize_float_range(
            config.auto_add_protected_stop_roe,
            DEFAULT_AUTO_ADD_PROTECTED_STOP_ROE,
            min_value=MIN_AUTO_ADD_PROTECTED_STOP_ROE,
            max_value=MAX_AUTO_ADD_PROTECTED_STOP_ROE,
        )
        include_entry_timing_15m_chart = _normalize_bool(config.include_entry_timing_15m_chart)
        use_all_monitored_interval_charts = _normalize_bool(config.use_all_monitored_interval_charts)
        reverse_order_enabled = _normalize_bool(config.reverse_order_enabled)
        prompt_map = _normalize_prompt_map(config.vegas_prompt_configs)
        return replace(
            config,
            execution_mode=mode,
            ema_interval_seconds=ema_interval,
            quant_interval_seconds=quant_interval,
            pending_entry_timeout_seconds=pending_entry_timeout_seconds,
            max_positions=max_positions,
            provider=provider or None,
            model=model or None,
            auto_add_enabled=auto_add_enabled,
            auto_add_trigger_atr_multiple=auto_add_trigger_atr_multiple,
            auto_add_tranche_margin_pct=auto_add_tranche_margin_pct,
            auto_add_max_tranches=auto_add_max_tranches,
            auto_add_protected_stop_roe=auto_add_protected_stop_roe,
            reasoning_effort=reasoning_effort,
            include_entry_timing_15m_chart=include_entry_timing_15m_chart,
            use_all_monitored_interval_charts=use_all_monitored_interval_charts,
            reverse_order_enabled=reverse_order_enabled,
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


def _normalize_pending_entry_timeout(value: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed < MIN_PENDING_ENTRY_TIMEOUT_SECONDS:
        return MIN_PENDING_ENTRY_TIMEOUT_SECONDS
    if parsed > MAX_PENDING_ENTRY_TIMEOUT_SECONDS:
        return MAX_PENDING_ENTRY_TIMEOUT_SECONDS
    return parsed


def _normalize_max_positions(value: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed < MIN_MAX_POSITIONS:
        return MIN_MAX_POSITIONS
    if parsed > MAX_MAX_POSITIONS:
        return MAX_MAX_POSITIONS
    return parsed


def _normalize_int_range(value: int, default: int, *, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed < min_value:
        return min_value
    if parsed > max_value:
        return max_value
    return parsed


def _normalize_float_range(
    value: float,
    default: float,
    *,
    min_value: float,
    max_value: float,
) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if parsed < min_value:
        return min_value
    if parsed > max_value:
        return max_value
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


def _normalize_reasoning_effort(value: object, *, provider: Optional[str]) -> Optional[str]:
    provider_key = (provider or "").strip().lower()
    if isinstance(value, str):
        normalized = value.strip().lower()
    else:
        normalized = ""
    if normalized not in CODEX_REASONING_EFFORTS:
        normalized = ""
    if provider_key == "codex":
        return normalized or DEFAULT_CODEX_REASONING_EFFORT
    return normalized or None
