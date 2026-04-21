from dataclasses import replace
from typing import Any, Dict, List, Optional, Set

from app.domain.llm_response_worker.models import ExecutionIdea
from app.application.risk_management.config_service import RiskManagementConfigService
from app.domain.risk_management.models import DEFAULT_RISK_MANAGEMENT_CONFIG
from app.domain.trade_guard.guard import GuardResult
from app.domain.trade_guard.interfaces import TradeGuardConfigRepository
from app.domain.trade_guard.models import (
    DEFAULT_TRADE_GUARD_CONFIG,
    LeverageTier,
    PositionTierRange,
    TradeGuardConfig,
)
from app.domain.trade_guard.rules import create_default_guard


class TradeGuardService:
    def __init__(
        self,
        config_repository: TradeGuardConfigRepository,
        risk_config_service: RiskManagementConfigService,
    ) -> None:
        self._config_repository = config_repository
        self._risk_config_service = risk_config_service

    async def get_config(self) -> TradeGuardConfig:
        config = await self._config_repository.get_config()
        if config is None:
            config = await self._config_repository.upsert(DEFAULT_TRADE_GUARD_CONFIG)
        return self._normalize_config(config)

    async def update_config(self, config: TradeGuardConfig) -> TradeGuardConfig:
        normalized = self._normalize_config(config)
        return await self._config_repository.upsert(normalized)

    async def get_exposure_pct(self) -> float:
        config = await self._risk_config_service.get_config()
        try:
            return float(config.exposure_pct)
        except (TypeError, ValueError):
            return float(DEFAULT_RISK_MANAGEMENT_CONFIG.exposure_pct)

    async def validate(
        self,
        decision: ExecutionIdea,
        account_state: Optional[Dict[str, Any]] = None,
        market_data: Optional[Dict[str, Any]] = None,
        open_orders: Optional[List[Dict[str, Any]]] = None,
        open_positions: Optional[List[Dict[str, Any]]] = None,
        pending_entries: Optional[List[Dict[str, Any]]] = None,
        price_fetcher: Optional[Any] = None,
        tradeable_symbols: Optional[Set[str]] = None,
        max_positions: Optional[int] = None,
        inflight_market_open_count: int = 0,
    ) -> GuardResult:
        config = await self.get_config()
        exposure_pct = await self.get_exposure_pct()
        guard = create_default_guard(config, tradeable_symbols=tradeable_symbols)
        return guard.validate(
            decision=decision,
            account_state=account_state,
            market_data=market_data,
            open_orders=open_orders,
            open_positions=open_positions,
            pending_entries=pending_entries,
            price_fetcher=price_fetcher,
            portfolio_exposure_pct=exposure_pct,
            max_positions=max_positions,
            inflight_market_open_count=inflight_market_open_count,
        )

    def _normalize_config(self, config: TradeGuardConfig) -> TradeGuardConfig:
        min_confidence = _normalize_percentage(
            config.min_confidence,
            DEFAULT_TRADE_GUARD_CONFIG.min_confidence,
        )
        min_position_size = _normalize_positive(
            config.min_position_size,
            DEFAULT_TRADE_GUARD_CONFIG.min_position_size,
        )
        sl_min_roe, sl_max_roe = _normalize_roe_pair(
            config.sl_min_roe,
            config.sl_max_roe,
            DEFAULT_TRADE_GUARD_CONFIG.sl_min_roe,
            DEFAULT_TRADE_GUARD_CONFIG.sl_max_roe,
        )
        tp_min_roe, tp_max_roe = _normalize_roe_pair(
            config.tp_min_roe,
            config.tp_max_roe,
            DEFAULT_TRADE_GUARD_CONFIG.tp_min_roe,
            DEFAULT_TRADE_GUARD_CONFIG.tp_max_roe,
            allow_zero_min=True,
        )
        dust_threshold = _normalize_positive(
            config.dust_threshold_usd,
            DEFAULT_TRADE_GUARD_CONFIG.dust_threshold_usd,
        )
        default_leverage = _normalize_leverage(
            config.default_leverage,
            DEFAULT_TRADE_GUARD_CONFIG.default_leverage,
        )
        leverage_tiers = _normalize_leverage_tiers(config.leverage_tiers)
        position_tier_ranges = _normalize_position_tier_ranges(config.position_tier_ranges)

        return replace(
            config,
            min_confidence=min_confidence,
            min_position_size=min_position_size,
            sl_min_roe=sl_min_roe,
            sl_max_roe=sl_max_roe,
            tp_min_roe=tp_min_roe,
            tp_max_roe=tp_max_roe,
            dust_threshold_usd=dust_threshold,
            default_leverage=default_leverage,
            leverage_tiers=leverage_tiers,
            position_tier_ranges=position_tier_ranges,
        )


def _normalize_percentage(value: float, fallback: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    if parsed < 0:
        return 0.0
    if parsed > 100:
        return 100.0
    return parsed


def _normalize_positive(value: float, fallback: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    if parsed < 0:
        return 0.0
    return parsed


def _normalize_roe_pair(
    min_value: float,
    max_value: float,
    default_min: float,
    default_max: float,
    allow_zero_min: bool = False,
) -> tuple:
    try:
        min_parsed = float(min_value)
    except (TypeError, ValueError):
        min_parsed = default_min
    try:
        max_parsed = float(max_value)
    except (TypeError, ValueError):
        max_parsed = default_max

    if allow_zero_min:
        if min_parsed < 0:
            min_parsed = 0.0
    elif min_parsed <= 0:
        min_parsed = default_min
    if max_parsed <= 0:
        max_parsed = default_max
    if max_parsed < min_parsed:
        max_parsed = min_parsed
    return min_parsed, max_parsed


def _normalize_leverage_tiers(tiers: List[LeverageTier]) -> List[LeverageTier]:
    grouped: dict[int, set[str]] = {}
    for tier in tiers:
        try:
            leverage = int(tier.leverage)
        except (TypeError, ValueError):
            continue
        if leverage <= 0:
            continue
        symbols = {symbol.strip().upper() for symbol in tier.symbols if str(symbol).strip()}
        if leverage not in grouped:
            grouped[leverage] = set()
        grouped[leverage].update(symbols)

    normalized: List[LeverageTier] = []
    for leverage in sorted(grouped.keys(), reverse=True):
        normalized.append(LeverageTier(leverage=leverage, symbols=sorted(grouped[leverage])))
    return normalized


def _normalize_leverage(value: float, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    if parsed < 1:
        return 1
    if parsed > 5:
        return 5
    return parsed


def _normalize_position_tier_ranges(tiers: List[PositionTierRange]) -> List[PositionTierRange]:
    grouped: dict[int, PositionTierRange] = {}
    for entry in tiers:
        try:
            tier = int(entry.tier)
            min_pct = float(entry.min_pct)
            max_pct = float(entry.max_pct)
        except (TypeError, ValueError):
            continue
        if tier <= 0:
            continue

        min_pct = max(0.0, min(1.0, min_pct))
        max_pct = max(0.0, min(1.0, max_pct))
        if max_pct < min_pct:
            min_pct, max_pct = max_pct, min_pct
        grouped[tier] = PositionTierRange(tier=tier, min_pct=min_pct, max_pct=max_pct)

    return [grouped[tier] for tier in sorted(grouped.keys())]
