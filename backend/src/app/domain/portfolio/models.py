from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass(frozen=True)
class ExchangeAccount:
    id: str
    name: str
    exchange: str
    is_active: bool
    is_testnet: bool
    created_at: datetime
    updated_at: datetime
    wallet_address: Optional[str] = None
    validation_status: str = "unvalidated"
    last_validated_at: Optional[datetime] = None
    validation_error: Optional[str] = None


@dataclass(frozen=True)
class ExchangeCredentials:
    account_id: str
    api_key: str
    api_secret: str
    passphrase: Optional[str] = None
    agent_key: Optional[str] = None


@dataclass(frozen=True)
class AccountSetup:
    portfolio_exposure_pct: float


@dataclass(frozen=True)
class AccountState:
    account_value: float
    available_margin: float
    total_margin_used: float
    unrealized_pnl: float
    open_positions_count: int
    total_exposure_pct: float


@dataclass(frozen=True)
class Position:
    symbol: str
    direction: str
    size: float
    entry_price: Optional[float]
    mark_price: Optional[float]
    unrealized_pnl: Optional[float]
    liquidation_price: Optional[float]
    margin: Optional[float]
    leverage: Optional[float]
    opened_at: Optional[datetime] = None


@dataclass(frozen=True)
class PortfolioSnapshot:
    account: ExchangeAccount
    state: AccountState
    positions: List[Position]


@dataclass(frozen=True)
class DailyPnlSnapshot:
    realized_pnl: float
    trade_count: int
    fills: List[dict]
    exchange: Optional[str] = None


@dataclass(frozen=True)
class MarketCandle:
    timestamp_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class MarketDataPoint:
    timestamp_ms: int
    value: float


@dataclass(frozen=True)
class MarketQuote:
    price: float
    change_percent: Optional[float] = None


@dataclass(frozen=True)
class OrderBookLevel:
    price: float
    size: float


@dataclass(frozen=True)
class OrderBookSnapshot:
    symbol: str
    timestamp_ms: int
    bids: List[OrderBookLevel]
    asks: List[OrderBookLevel]


@dataclass(frozen=True)
class FundingRateSnapshot:
    rate: float
    timestamp_ms: int
    next_funding_time_ms: Optional[int] = None
    mark_price: Optional[float] = None
