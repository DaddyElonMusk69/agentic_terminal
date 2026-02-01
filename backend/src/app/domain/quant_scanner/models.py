from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from app.domain.portfolio.models import MarketCandle, MarketDataPoint, FundingRateSnapshot


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class QuantScannerConfig:
    assets: List[str]
    timeframes: List[str]
    quote_asset: str = "USDT"


@dataclass(frozen=True)
class DepthMetrics:
    bid_volume_usd: float
    ask_volume_usd: float
    net_depth_usd: float
    imbalance_pct: float
    obi_ratio: Optional[float]
    mid_price: Optional[float]
    range_pct: float
    best_bid: Optional[float] = None
    best_ask: Optional[float] = None


@dataclass(frozen=True)
class VwapMetrics:
    value: float
    std_dev: float
    distance: float
    candle_count: int


@dataclass(frozen=True)
class AtrMetrics:
    value: float
    slope_pct: float
    z_score: Optional[float]
    period: int
    lookback: int


@dataclass(frozen=True)
class NetflowMetrics:
    institution_netflow: float
    retail_netflow: float
    total_netflow: float
    flow_regime: str
    dominant_flow: str
    timeframe: str

    @classmethod
    def from_api_response(cls, data: Dict[str, Any], timeframe: str) -> Optional["NetflowMetrics"]:
        if not data:
            return None

        inner = data.get("data", data)
        netflow = inner.get("netflow", {})
        institution = netflow.get("institution", {}).get("future", {})
        retail = netflow.get("personal", {}).get("future", {})

        inst_value = institution.get(timeframe)
        retail_value = retail.get(timeframe)

        if inst_value is None and retail_value is None:
            return None

        inst_value = float(inst_value or 0.0)
        retail_value = float(retail_value or 0.0)
        total = inst_value + retail_value

        flow_regime = _classify_flow_regime(total)
        dominant_flow = "institution" if abs(inst_value) >= abs(retail_value) else "retail"

        return cls(
            institution_netflow=inst_value,
            retail_netflow=retail_value,
            total_netflow=total,
            flow_regime=flow_regime,
            dominant_flow=dominant_flow,
            timeframe=timeframe,
        )


def _classify_flow_regime(total_netflow: float) -> str:
    strong_threshold = 1_000_000
    moderate_threshold = 100_000

    if total_netflow > strong_threshold:
        return "strong_inflow"
    if total_netflow > moderate_threshold:
        return "moderate_inflow"
    if total_netflow >= -moderate_threshold:
        return "neutral"
    if total_netflow >= -strong_threshold:
        return "moderate_outflow"
    return "strong_outflow"


@dataclass(frozen=True)
class AnomalyResult:
    factor: str
    anomaly_type: str
    z_score: float
    magnitude_pct: float
    baseline_mean: float
    baseline_std: float
    threshold: float
    is_significant: bool
    current_value: float
    insufficient_data: bool = False


@dataclass(frozen=True)
class AnomalySnapshot:
    price: AnomalyResult
    open_interest: AnomalyResult
    cvd: AnomalyResult


@dataclass(frozen=True)
class QuantSnapshot:
    symbol: str
    timeframe: str
    timestamp: datetime = field(default_factory=_utcnow)

    candles: List[MarketCandle] = field(default_factory=list)
    prices: List[float] = field(default_factory=list)
    open_interest: List[MarketDataPoint] = field(default_factory=list)
    cvd: List[float] = field(default_factory=list)
    cvd_deltas: List[float] = field(default_factory=list)

    price_current: Optional[float] = None
    oi_current: Optional[float] = None
    cvd_current: Optional[float] = None

    funding_rate: Optional[FundingRateSnapshot] = None
    order_book: Optional[DepthMetrics] = None
    vwap: Optional[VwapMetrics] = None
    atr: Optional[AtrMetrics] = None
    netflow: Optional[NetflowMetrics] = None
    anomalies: Optional[AnomalySnapshot] = None
    price_slope: Optional[float] = None
    price_slope_z: Optional[float] = None
    oi_slope: Optional[float] = None
    oi_slope_z: Optional[float] = None
    cvd_slope: Optional[float] = None
    cvd_slope_z: Optional[float] = None
