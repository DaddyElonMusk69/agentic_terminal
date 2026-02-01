from functools import lru_cache

from app.application.circuit_breaker.service import CircuitBreakerService
from app.domain.circuit_breaker.engine import CircuitBreaker


@lru_cache(maxsize=1)
def get_circuit_breaker_service() -> CircuitBreakerService:
    return CircuitBreakerService(CircuitBreaker())
