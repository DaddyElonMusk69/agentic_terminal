from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class AutomationSessionRecord:
    id: str
    started_at: datetime
    ended_at: Optional[datetime]
    execution_mode: str
    provider: Optional[str]
    model: Optional[str]
    total_cycles: int
    total_trades: int
    total_pnl: float
    prompt_count: int
    config_snapshot: Optional[dict]


@dataclass(frozen=True)
class AutomationLogRecord:
    id: int
    session_id: str
    created_at: datetime
    log_type: str
    cycle_number: int
    data: Optional[dict]


@dataclass(frozen=True)
class AutomationTradeRecord:
    id: int
    session_id: str
    created_at: datetime
    cycle_number: int
    symbol: str
    direction: Optional[str]
    action: Optional[str]
    entry_price: Optional[float]
    exit_price: Optional[float]
    size_usd: Optional[float]
    pnl: Optional[float]
    pnl_pct: Optional[float]
    status: Optional[str]
    closed_at: Optional[datetime]
    signal_data: Optional[dict]
    llm_reasoning: Optional[str]
    llm_response_full: Optional[str]
    order_id: Optional[str]
    fill_price: Optional[float]
