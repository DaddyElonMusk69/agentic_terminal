from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class LeverageTier:
    leverage: int
    symbols: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class PositionTierRange:
    tier: int
    min_pct: float
    max_pct: float


@dataclass(frozen=True)
class TradeGuardConfig:
    min_confidence: float
    min_position_size: float
    sl_min_roe: float
    sl_max_roe: float
    tp_min_roe: float
    tp_max_roe: float
    dust_threshold_usd: float
    default_leverage: int
    leverage_tiers: List[LeverageTier]
    position_tier_ranges: List[PositionTierRange]


DEFAULT_TRADE_GUARD_CONFIG = TradeGuardConfig(
    min_confidence=60.0,
    min_position_size=10.0,
    sl_min_roe=0.03,
    sl_max_roe=0.05,
    tp_min_roe=0.05,
    tp_max_roe=0.2,
    dust_threshold_usd=10.0,
    default_leverage=1,
    leverage_tiers=[
        LeverageTier(
            leverage=5,
            symbols=["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE"],
        ),
        LeverageTier(
            leverage=3,
            symbols=["SUI", "FARTCOIN", "LTC", "BCH", "XRP"],
        ),
    ],
    position_tier_ranges=[
        PositionTierRange(tier=1, min_pct=0.70, max_pct=1.00),
        PositionTierRange(tier=2, min_pct=0.35, max_pct=0.70),
        PositionTierRange(tier=3, min_pct=0.15, max_pct=0.35),
    ],
)
