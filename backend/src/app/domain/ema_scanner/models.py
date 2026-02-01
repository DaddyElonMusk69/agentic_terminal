from dataclasses import dataclass
from datetime import datetime
from typing import List


@dataclass(frozen=True)
class EmaScannerLine:
    id: int
    length: int


@dataclass(frozen=True)
class EmaScannerConfig:
    assets: List[str]
    timeframes: List[str]
    ema_lengths: List[int]
    tolerance_pct: float
    quote_asset: str = "USDT"
    min_candles: int = 20
    candles_multiplier: int = 3
    max_candles: int = 1499


@dataclass(frozen=True)
class EmaScannerSignal:
    symbol: str
    timeframe: str
    indicator: str
    parameter: str
    value: float
    price: float
    lower_bound: float
    upper_bound: float
    condition: str
    timestamp: datetime
