from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class RuleSeverity(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class RuleCategory(Enum):
    REQUIRED_FIELDS = "required_fields"
    POSITION_SIZING = "position_sizing"
    RISK_MANAGEMENT = "risk_management"
    MARKET_CONDITIONS = "market_conditions"
    ACCOUNT_STATE = "account_state"
    SYMBOL_VALIDATION = "symbol_validation"
    CONFIDENCE = "confidence"
    CUSTOM = "custom"


@dataclass
class RuleResult:
    rule_name: str
    passed: bool
    severity: RuleSeverity
    category: RuleCategory
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_name": self.rule_name,
            "passed": self.passed,
            "severity": self.severity.value,
            "category": self.category.value,
            "message": self.message,
            "details": self.details,
        }


@dataclass
class ModificationResult:
    modifier_name: str
    modified: bool
    field_name: str = ""
    original_value: Any = None
    new_value: Any = None
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "modifier_name": self.modifier_name,
            "modified": self.modified,
            "field_name": self.field_name,
            "original_value": self.original_value,
            "new_value": self.new_value,
            "reason": self.reason,
        }


@dataclass
class GuardResult:
    is_valid: bool
    decision: Any = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    modifications: List[ModificationResult] = field(default_factory=list)
    rule_results: List[RuleResult] = field(default_factory=list)
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "modifications": [item.to_dict() for item in self.modifications],
            "rule_results": [item.to_dict() for item in self.rule_results],
            "checked_at": self.checked_at.isoformat(),
        }

    def get_failed_rules(self) -> List[RuleResult]:
        return [result for result in self.rule_results if not result.passed]

    def get_rules_by_category(self, category: RuleCategory) -> List[RuleResult]:
        return [result for result in self.rule_results if result.category == category]

    @property
    def was_modified(self) -> bool:
        return any(item.modified for item in self.modifications)


@dataclass
class GuardContext:
    decision: Any
    account_state: Optional[Dict[str, Any]] = None
    market_data: Optional[Dict[str, Any]] = None
    open_positions: Optional[List[Dict[str, Any]]] = None
    recent_trades: Optional[List[Dict[str, Any]]] = None
    config: Optional[Dict[str, Any]] = None
    price_fetcher: Optional[Any] = None
    portfolio_exposure_pct: Optional[float] = None

    def get_config_value(self, key: str, default: Any = None) -> Any:
        if self.config is None:
            return default
        return self.config.get(key, default)

    def get_current_price(self, symbol: str) -> Optional[float]:
        if self.price_fetcher is None:
            return None
        try:
            return self.price_fetcher(symbol)
        except Exception:
            return None

    def get_portfolio_exposure_pct(self, default: float = 25.0) -> float:
        if self.portfolio_exposure_pct is not None:
            return self.portfolio_exposure_pct
        if self.account_state and self.account_state.get("portfolio_exposure_pct") is not None:
            return float(self.account_state["portfolio_exposure_pct"])
        return default


class ValidationRule(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def category(self) -> RuleCategory:
        ...

    @property
    def severity(self) -> RuleSeverity:
        return RuleSeverity.ERROR

    @property
    def description(self) -> str:
        return ""

    @property
    def enabled(self) -> bool:
        return True

    @abstractmethod
    def check(self, context: GuardContext) -> RuleResult:
        ...

    def _pass(self, message: str = "", details: Dict[str, Any] | None = None) -> RuleResult:
        return RuleResult(
            rule_name=self.name,
            passed=True,
            severity=self.severity,
            category=self.category,
            message=message,
            details=details or {},
        )

    def _fail(self, message: str, details: Dict[str, Any] | None = None) -> RuleResult:
        return RuleResult(
            rule_name=self.name,
            passed=False,
            severity=self.severity,
            category=self.category,
            message=message,
            details=details or {},
        )


class ModifierRule(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    def description(self) -> str:
        return ""

    @property
    def enabled(self) -> bool:
        return True

    @abstractmethod
    def modify(self, decision: Any, context: GuardContext) -> tuple:
        ...

    def _no_change(self, decision: Any, reason: str = "") -> tuple:
        return decision, ModificationResult(
            modifier_name=self.name,
            modified=False,
            reason=reason,
        )

    def _modified(
        self,
        new_decision: Any,
        field_name: str,
        original_value: Any,
        new_value: Any,
        reason: str = "",
    ) -> tuple:
        return new_decision, ModificationResult(
            modifier_name=self.name,
            modified=True,
            field_name=field_name,
            original_value=original_value,
            new_value=new_value,
            reason=reason,
        )


class TradeGuard:
    def __init__(self) -> None:
        self._rules: List[ValidationRule] = []
        self._modifiers: List[ModifierRule] = []
        self._rule_names: Set[str] = set()
        self._modifier_names: Set[str] = set()

    def register_rule(self, rule: ValidationRule) -> "TradeGuard":
        if rule.name in self._rule_names:
            raise ValueError(f"Rule '{rule.name}' is already registered")
        self._rules.append(rule)
        self._rule_names.add(rule.name)
        return self

    def register_rules(self, rules: List[ValidationRule]) -> "TradeGuard":
        for rule in rules:
            self.register_rule(rule)
        return self

    def register_modifier(self, modifier: ModifierRule) -> "TradeGuard":
        if modifier.name in self._modifier_names:
            raise ValueError(f"Modifier '{modifier.name}' is already registered")
        self._modifiers.append(modifier)
        self._modifier_names.add(modifier.name)
        return self

    def unregister_rule(self, rule_name: str) -> bool:
        for i, rule in enumerate(self._rules):
            if rule.name == rule_name:
                self._rules.pop(i)
                self._rule_names.remove(rule_name)
                return True
        return False

    def unregister_modifier(self, modifier_name: str) -> bool:
        for i, modifier in enumerate(self._modifiers):
            if modifier.name == modifier_name:
                self._modifiers.pop(i)
                self._modifier_names.remove(modifier_name)
                return True
        return False

    def get_rules(self, category: Optional[RuleCategory] = None) -> List[ValidationRule]:
        if category is None:
            return list(self._rules)
        return [rule for rule in self._rules if rule.category == category]

    def get_modifiers(self) -> List[ModifierRule]:
        return list(self._modifiers)

    def validate(
        self,
        decision: Any,
        account_state: Optional[Dict[str, Any]] = None,
        market_data: Optional[Dict[str, Any]] = None,
        open_positions: Optional[List[Dict[str, Any]]] = None,
        recent_trades: Optional[List[Dict[str, Any]]] = None,
        config: Optional[Dict[str, Any]] = None,
        price_fetcher: Optional[Any] = None,
        portfolio_exposure_pct: Optional[float] = None,
    ) -> GuardResult:
        context = GuardContext(
            decision=decision,
            account_state=account_state,
            market_data=market_data,
            open_positions=open_positions,
            recent_trades=recent_trades,
            config=config,
            price_fetcher=price_fetcher,
            portfolio_exposure_pct=portfolio_exposure_pct,
        )

        errors: List[str] = []
        warnings: List[str] = []
        rule_results: List[RuleResult] = []
        modifications: List[ModificationResult] = []

        for rule in self._rules:
            if not rule.enabled:
                continue
            try:
                result = rule.check(context)
                rule_results.append(result)
                if not result.passed:
                    if result.severity == RuleSeverity.ERROR:
                        errors.append(result.message)
                    elif result.severity == RuleSeverity.WARNING:
                        warnings.append(result.message)
                    logger.debug(
                        "TradeGuard rule failed: %s (%s)",
                        result.message,
                        result.severity.value,
                    )
            except Exception as exc:
                error_msg = f"Rule '{rule.name}' raised exception: {exc}"
                errors.append(error_msg)
                rule_results.append(
                    RuleResult(
                        rule_name=rule.name,
                        passed=False,
                        severity=RuleSeverity.ERROR,
                        category=rule.category,
                        message=error_msg,
                        details={"exception": str(exc)},
                    )
                )
                logger.exception("TradeGuard rule exception: %s", rule.name)

        is_valid = len(errors) == 0
        current_decision = decision

        if is_valid:
            for modifier in self._modifiers:
                if not modifier.enabled:
                    continue
                try:
                    current_decision, mod_result = modifier.modify(current_decision, context)
                    modifications.append(mod_result)
                except Exception as exc:
                    logger.exception("TradeGuard modifier exception: %s", modifier.name)
                    modifications.append(
                        ModificationResult(
                            modifier_name=modifier.name,
                            modified=False,
                            reason=f"Exception: {exc}",
                        )
                    )

        return GuardResult(
            is_valid=is_valid,
            decision=current_decision,
            errors=errors,
            warnings=warnings,
            modifications=modifications,
            rule_results=rule_results,
        )

    def __len__(self) -> int:
        return len(self._rules) + len(self._modifiers)

    def __repr__(self) -> str:
        return f"TradeGuard(rules={len(self._rules)}, modifiers={len(self._modifiers)})"
