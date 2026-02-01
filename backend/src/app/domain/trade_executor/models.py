from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class ExecutionResult:
    success: bool
    status: str
    order_id: Optional[str] = None
    fill_price: Optional[float] = None
    filled_size: Optional[float] = None
    realized_pnl: Optional[float] = None
    error: Optional[str] = None
    raw_response: Optional[Any] = None
