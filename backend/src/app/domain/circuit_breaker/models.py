from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class CircuitBreakerContext:
    decision: Any
    account_state: Optional[Dict[str, Any]] = None
    market_data: Optional[Dict[str, Any]] = None
    open_positions: Optional[List[Dict[str, Any]]] = None


@dataclass(frozen=True)
class CircuitBreakerResult:
    allowed: bool
    decision: Any
    reasons: List[str] = field(default_factory=list)
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
