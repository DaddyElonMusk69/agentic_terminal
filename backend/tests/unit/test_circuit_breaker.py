from app.application.circuit_breaker.service import CircuitBreakerService
from app.domain.llm_response_worker.models import ExecutionAction, ExecutionIdea


def test_circuit_breaker_allows_by_default():
    service = CircuitBreakerService()
    decision = ExecutionIdea(action=ExecutionAction.HOLD, symbol="BTC")
    result = service.evaluate(decision)
    assert result.allowed is True
