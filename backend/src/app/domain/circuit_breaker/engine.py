from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from app.domain.circuit_breaker.models import CircuitBreakerContext, CircuitBreakerResult


class CircuitBreakerRule(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def check(self, context: CircuitBreakerContext) -> CircuitBreakerResult | None:
        ...


class CircuitBreaker:
    def __init__(self) -> None:
        self._rules: List[CircuitBreakerRule] = []

    def register_rule(self, rule: CircuitBreakerRule) -> "CircuitBreaker":
        self._rules.append(rule)
        return self

    def evaluate(self, context: CircuitBreakerContext) -> CircuitBreakerResult:
        for rule in self._rules:
            result = rule.check(context)
            if result is not None and not result.allowed:
                return result

        return CircuitBreakerResult(
            allowed=True,
            decision=context.decision,
            reasons=[],
        )
