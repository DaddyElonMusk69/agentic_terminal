from typing import Any, Dict, List, Optional

from app.domain.circuit_breaker.engine import CircuitBreaker
from app.domain.circuit_breaker.models import CircuitBreakerContext, CircuitBreakerResult


class CircuitBreakerService:
    def __init__(self, breaker: Optional[CircuitBreaker] = None) -> None:
        self._breaker = breaker or CircuitBreaker()

    def evaluate(
        self,
        decision: Any,
        account_state: Optional[Dict[str, Any]] = None,
        market_data: Optional[Dict[str, Any]] = None,
        open_positions: Optional[List[Dict[str, Any]]] = None,
    ) -> CircuitBreakerResult:
        context = CircuitBreakerContext(
            decision=decision,
            account_state=account_state,
            market_data=market_data,
            open_positions=open_positions,
        )
        return self._breaker.evaluate(context)
