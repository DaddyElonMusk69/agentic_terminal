from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, Optional, Set

from app.domain.llm_response_worker.models import ExecutionAction, ExecutionIdea
from app.domain.trade_guard.guard import (
    GuardContext,
    ModifierRule,
    RuleCategory,
    RuleResult,
    RuleSeverity,
    TradeGuard,
    ValidationRule,
)
from app.domain.trade_guard.models import TradeGuardConfig


class ActionRequiredRule(ValidationRule):
    VALID_ACTIONS = set(ExecutionAction)

    @property
    def name(self) -> str:
        return "action_required"

    @property
    def category(self) -> RuleCategory:
        return RuleCategory.REQUIRED_FIELDS

    @property
    def description(self) -> str:
        return "Validates that action is present and is a valid ExecutionAction"

    def check(self, context: GuardContext) -> RuleResult:
        decision = context.decision
        if decision.action is None:
            return self._fail("Action is required")
        if decision.action not in self.VALID_ACTIONS:
            valid_actions = [action.value for action in self.VALID_ACTIONS]
            return self._fail(f"Invalid action: {decision.action}. Must be one of: {valid_actions}")
        return self._pass()


class SymbolRequiredRule(ValidationRule):
    @property
    def name(self) -> str:
        return "symbol_required"

    @property
    def category(self) -> RuleCategory:
        return RuleCategory.REQUIRED_FIELDS

    @property
    def description(self) -> str:
        return "Validates that symbol is present"

    def check(self, context: GuardContext) -> RuleResult:
        decision = context.decision
        if not decision.symbol:
            return self._fail("Symbol is required")
        return self._pass()


class OpenActionFieldsRule(ValidationRule):
    OPEN_ACTIONS = {
        ExecutionAction.OPEN_LONG,
        ExecutionAction.OPEN_SHORT,
    }

    @property
    def name(self) -> str:
        return "open_action_fields"

    @property
    def category(self) -> RuleCategory:
        return RuleCategory.REQUIRED_FIELDS

    @property
    def description(self) -> str:
        return "Validates OPEN actions have required fields"

    def check(self, context: GuardContext) -> RuleResult:
        decision = context.decision
        if decision.action not in self.OPEN_ACTIONS:
            return self._pass("Not an OPEN action")
        return self._pass()


class LimitOrderFieldsRule(ValidationRule):
    LIMIT_ACTIONS = {
        ExecutionAction.OPEN_LONG_LIMIT,
        ExecutionAction.OPEN_SHORT_LIMIT,
    }

    @property
    def name(self) -> str:
        return "limit_order_fields"

    @property
    def category(self) -> RuleCategory:
        return RuleCategory.REQUIRED_FIELDS

    @property
    def description(self) -> str:
        return "Validates OPEN_LIMIT actions have limit_price"

    def check(self, context: GuardContext) -> RuleResult:
        decision = context.decision
        if decision.action not in self.LIMIT_ACTIONS:
            return self._pass("Not a LIMIT action")

        errors = []
        if decision.limit_price is None:
            errors.append(f"{decision.action.value} requires limit_price")
        elif decision.limit_price <= 0:
            errors.append(f"limit_price must be > 0, got {decision.limit_price}")

        if errors:
            return self._fail("; ".join(errors))
        return self._pass()


class ReduceActionFieldsRule(ValidationRule):
    @property
    def name(self) -> str:
        return "reduce_action_fields"

    @property
    def category(self) -> RuleCategory:
        return RuleCategory.REQUIRED_FIELDS

    @property
    def description(self) -> str:
        return "Validates REDUCE action has valid reduce_pct"

    def check(self, context: GuardContext) -> RuleResult:
        decision = context.decision
        if decision.action != ExecutionAction.REDUCE:
            return self._pass("Not a REDUCE action")
        if decision.reduce_pct is None:
            return self._fail("REDUCE action requires reduce_pct")
        if decision.reduce_pct <= 0 or decision.reduce_pct > 100:
            return self._fail(f"reduce_pct must be between 0 and 100, got {decision.reduce_pct}")
        return self._pass()


class UpdateSLFieldsRule(ValidationRule):
    @property
    def name(self) -> str:
        return "update_sl_fields"

    @property
    def category(self) -> RuleCategory:
        return RuleCategory.REQUIRED_FIELDS

    @property
    def description(self) -> str:
        return "Validates UPDATE_SL action has valid new_stop_loss"

    def check(self, context: GuardContext) -> RuleResult:
        decision = context.decision
        if decision.action != ExecutionAction.UPDATE_SL:
            return self._pass("Not an UPDATE_SL action")
        if decision.new_stop_loss is None:
            return self._fail("UPDATE_SL action requires new_stop_loss")
        if decision.new_stop_loss <= 0:
            return self._fail(f"new_stop_loss must be > 0, got {decision.new_stop_loss}")
        return self._pass()


class UpdateTPFieldsRule(ValidationRule):
    @property
    def name(self) -> str:
        return "update_tp_fields"

    @property
    def category(self) -> RuleCategory:
        return RuleCategory.REQUIRED_FIELDS

    @property
    def description(self) -> str:
        return "Validates UPDATE_TP action has valid new_take_profit"

    def check(self, context: GuardContext) -> RuleResult:
        decision = context.decision
        if decision.action != ExecutionAction.UPDATE_TP:
            return self._pass("Not an UPDATE_TP action")
        if decision.new_take_profit is None:
            return self._fail("UPDATE_TP action requires new_take_profit")
        if decision.new_take_profit <= 0:
            return self._fail(f"new_take_profit must be > 0, got {decision.new_take_profit}")
        return self._pass()


class MinConfidenceRule(ValidationRule):
    ACTIONABLE_ACTIONS = {
        ExecutionAction.OPEN_LONG,
        ExecutionAction.OPEN_SHORT,
        ExecutionAction.OPEN_LONG_LIMIT,
        ExecutionAction.OPEN_SHORT_LIMIT,
        ExecutionAction.CLOSE,
        ExecutionAction.REDUCE,
    }

    def __init__(self, min_confidence: float = 60.0) -> None:
        self._min_confidence = min_confidence

    @property
    def name(self) -> str:
        return "min_confidence"

    @property
    def category(self) -> RuleCategory:
        return RuleCategory.CONFIDENCE

    @property
    def description(self) -> str:
        return f"Validates confidence is at least {self._min_confidence}%"

    def check(self, context: GuardContext) -> RuleResult:
        decision = context.decision
        if decision.action == ExecutionAction.HOLD:
            return self._pass("HOLD action doesn't require confidence check")
        if decision.action not in self.ACTIONABLE_ACTIONS:
            return self._pass("Non-actionable action")

        confidence = decision.confidence if decision.confidence is not None else 0.0
        if confidence < self._min_confidence:
            return self._fail(
                f"Confidence {confidence}% is below minimum threshold {self._min_confidence}%",
                details={"confidence": confidence, "min_confidence": self._min_confidence},
            )
        return self._pass()


class TradeableSymbolRule(ValidationRule):
    def __init__(self, tradeable_symbols: Optional[Set[str]] = None) -> None:
        self._tradeable_symbols = tradeable_symbols

    @property
    def name(self) -> str:
        return "tradeable_symbol"

    @property
    def category(self) -> RuleCategory:
        return RuleCategory.SYMBOL_VALIDATION

    @property
    def description(self) -> str:
        return "Validates symbol is tradeable"

    @property
    def enabled(self) -> bool:
        return self._tradeable_symbols is not None

    def check(self, context: GuardContext) -> RuleResult:
        decision = context.decision
        if self._tradeable_symbols is None:
            return self._pass("No symbol restrictions")
        if not decision.symbol:
            return self._pass("No symbol to check")
        symbol_upper = decision.symbol.upper()
        if symbol_upper not in self._tradeable_symbols:
            return self._fail(
                f"Symbol {decision.symbol} is not tradeable",
                details={"symbol": decision.symbol},
            )
        return self._pass()


class MaxLeverageModifier(ModifierRule):
    OPEN_ACTIONS = {
        ExecutionAction.OPEN_LONG,
        ExecutionAction.OPEN_SHORT,
        ExecutionAction.OPEN_LONG_LIMIT,
        ExecutionAction.OPEN_SHORT_LIMIT,
    }

    def __init__(
        self,
        leverage_tiers: Optional[Dict[int, Set[str]]] = None,
        default_leverage: int = 1,
    ) -> None:
        self._leverage_tiers = leverage_tiers or {}
        try:
            parsed_default = int(default_leverage)
        except (TypeError, ValueError):
            parsed_default = 1
        self._default_leverage = max(1, parsed_default)

    @property
    def name(self) -> str:
        return "max_leverage"

    @property
    def description(self) -> str:
        return "Restricts leverage based on symbol tiers"

    def modify(self, decision: ExecutionIdea, context: GuardContext) -> tuple:
        if decision.action not in self.OPEN_ACTIONS:
            return self._no_change(decision, "Not an OPEN action")

        symbol = decision.symbol.upper() if decision.symbol else ""
        if not symbol:
            return self._no_change(decision, "No symbol specified")

        requested_leverage = decision.leverage or 1
        matched_leverage: Optional[int] = None

        for leverage, symbols in self._leverage_tiers.items():
            if symbol in symbols:
                matched_leverage = leverage if matched_leverage is None else max(matched_leverage, leverage)

        allowed_leverage = matched_leverage if matched_leverage is not None else self._default_leverage

        if requested_leverage != allowed_leverage:
            new_decision = replace(decision, leverage=allowed_leverage)
            reason = (
                f"Assigned leverage for {symbol}: {requested_leverage}x → {allowed_leverage}x"
                if requested_leverage < allowed_leverage
                else (
                    f"Restricted leverage for {symbol}: {requested_leverage}x → "
                    f"{allowed_leverage}x (Max permitted)"
                )
            )
            return self._modified(
                new_decision,
                field_name="leverage",
                original_value=requested_leverage,
                new_value=allowed_leverage,
                reason=reason,
            )

        return self._no_change(
            decision,
            f"Leverage {requested_leverage}x matches assigned ({allowed_leverage}x) for {symbol}",
        )


class TierBasedPositionSizeModifier(ModifierRule):
    OPEN_ACTIONS = {
        ExecutionAction.OPEN_LONG,
        ExecutionAction.OPEN_SHORT,
        ExecutionAction.OPEN_LONG_LIMIT,
        ExecutionAction.OPEN_SHORT_LIMIT,
    }
    DEFAULT_TIER_RANGES = {
        1: (0.70, 1.00),
        2: (0.35, 0.70),
        3: (0.15, 0.35),
    }
    DEFAULT_TIER = 2

    def __init__(
        self,
        min_size_usd: float = 10.0,
        tier_ranges: Optional[Dict[int, tuple[float, float]]] = None,
        default_range: Optional[tuple[float, float]] = None,
    ) -> None:
        self._min_size = min_size_usd
        self._tier_ranges = tier_ranges or {}
        self._default_range = default_range or self.DEFAULT_TIER_RANGES[self.DEFAULT_TIER]

    @property
    def name(self) -> str:
        return "tier_position_size"

    @property
    def description(self) -> str:
        return f"Sets or clamps position size based on tier limits (min ${self._min_size:,.2f})"

    def _get_tier_range(self, tier: int) -> tuple[float, float]:
        return self._tier_ranges.get(tier, self._default_range)

    def _get_validated_position_pct(self, tier: int, position_pct: Optional[float]) -> tuple:
        min_pct, max_pct = self._get_tier_range(tier)
        if position_pct is None:
            return (min_pct, False, f"using tier {tier} default ({min_pct*100:.0f}%)")
        if position_pct < min_pct:
            return (min_pct, True, f"position_pct {position_pct*100:.0f}% below tier {tier} min ({min_pct*100:.0f}%)")
        if position_pct > max_pct:
            return (min_pct, True, f"position_pct {position_pct*100:.0f}% above tier {tier} max ({max_pct*100:.0f}%), defaulting to min")
        return (position_pct, False, f"position_pct {position_pct*100:.0f}% within tier {tier} range")

    def _apply_min_size_fallback(self, decision: ExecutionIdea, reason: str) -> tuple:
        if decision.position_size_usd is None:
            return self._no_change(decision, reason)
        if decision.position_size_usd < self._min_size:
            new_decision = replace(decision, position_size_usd=self._min_size)
            return self._modified(
                new_decision,
                field_name="position_size_usd",
                original_value=decision.position_size_usd,
                new_value=self._min_size,
                reason=f"{reason} - bumped to min ${self._min_size:,.2f}",
            )
        return self._no_change(decision, reason)

    def modify(self, decision: ExecutionIdea, context: GuardContext) -> tuple:
        if decision.action not in self.OPEN_ACTIONS:
            return self._no_change(decision, "Not an OPEN action")

        tier = decision.tier if decision.tier is not None else self.DEFAULT_TIER
        leverage = decision.leverage or 1
        if leverage <= 0:
            leverage = 1

        account_state = context.account_state or {}
        account_value = account_state.get("account_value", 0) or 0
        portfolio_exposure_pct = context.get_portfolio_exposure_pct()
        if account_value <= 0:
            return self._apply_min_size_fallback(decision, "No account value available")

        max_available_margin = account_value * (portfolio_exposure_pct / 100.0)
        if max_available_margin <= 0:
            return self._apply_min_size_fallback(decision, "No available margin")

        min_pct, max_pct = self._get_tier_range(tier)
        max_tier_size = max_available_margin * max_pct * leverage
        if max_tier_size <= 0:
            return self._apply_min_size_fallback(decision, "No tier size available")

        use_pct = decision.position_pct is not None or decision.position_size_usd is None
        if use_pct:
            validated_pct, was_adjusted, adjustment_reason = self._get_validated_position_pct(
                tier, decision.position_pct
            )
            proposed_size = max_available_margin * validated_pct * leverage
            basis_detail = (
                f"margin ${max_available_margin:,.2f} × {validated_pct*100:.0f}% × {leverage}x"
            )
        else:
            proposed_size = decision.position_size_usd or 0.0
            was_adjusted = False
            adjustment_reason = "using provided position_size_usd"
            basis_detail = f"max ${max_tier_size:,.2f}, min ${self._min_size:,.2f}"

        target_size = proposed_size
        clamp_notes = []

        if target_size < self._min_size:
            if max_tier_size < self._min_size:
                new_decision = replace(decision, action=ExecutionAction.HOLD, position_size_usd=None)
                return self._modified(
                    new_decision,
                    field_name="action",
                    original_value=decision.action.value,
                    new_value="HOLD",
                    reason=(
                        f"Tier {tier}: max ${max_tier_size:,.2f} below min ${self._min_size:,.2f}; HOLD"
                    ),
                )
            target_size = self._min_size
            clamp_notes.append(f"bumped to min ${self._min_size:,.2f}")

        if target_size > max_tier_size:
            target_size = max_tier_size
            clamp_notes.append(f"capped to tier max ${max_tier_size:,.2f}")

        original_size = decision.position_size_usd or 0.0
        new_decision = replace(decision, position_size_usd=target_size)

        reason_parts = [basis_detail, adjustment_reason]
        if clamp_notes:
            reason_parts.append(", ".join(clamp_notes))
        reason = (
            f"Tier {tier}: ${original_size:,.2f} -> ${target_size:,.2f} "
            f"({'; '.join(part for part in reason_parts if part)})"
        )

        if (
            was_adjusted
            or clamp_notes
            or decision.position_size_usd is None
            or abs(target_size - original_size) > 0.01
        ):
            return self._modified(
                new_decision,
                field_name="position_size_usd",
                original_value=original_size,
                new_value=target_size,
                reason=reason,
            )

        return self._no_change(new_decision, reason)


class ExchangeMinimumOrderSizeModifier(ModifierRule):
    OPEN_ACTIONS = {
        ExecutionAction.OPEN_LONG,
        ExecutionAction.OPEN_SHORT,
        ExecutionAction.OPEN_LONG_LIMIT,
        ExecutionAction.OPEN_SHORT_LIMIT,
    }

    @property
    def name(self) -> str:
        return "exchange_min_order_size"

    @property
    def description(self) -> str:
        return "Bumps position_size_usd to exchange minimum notional when required"

    def modify(self, decision: ExecutionIdea, context: GuardContext) -> tuple:
        if decision.action not in self.OPEN_ACTIONS:
            return self._no_change(decision, "Not an OPEN action")

        market_data = context.market_data or {}
        if not market_data:
            return self._no_change(decision, "No market_data available")

        min_notional = market_data.get("min_notional")
        reference_price = market_data.get("reference_price")
        min_amount = market_data.get("min_amount")
        contract_size = market_data.get("contract_size") or 1

        if not min_notional and min_amount and reference_price:
            min_notional = min_amount * reference_price * contract_size

        if not min_notional or min_notional <= 0:
            return self._no_change(decision, "No exchange minimum notional available")

        current_size = decision.position_size_usd or 0
        if current_size >= min_notional:
            return self._no_change(
                decision,
                f"Meets exchange minimum notional: ${current_size:,.2f} >= ${min_notional:,.2f}",
            )

        leverage = decision.leverage or 1
        required_margin = min_notional / leverage if leverage > 0 else min_notional
        exchange_name = market_data.get("exchange_name", "exchange")
        order_type = market_data.get("order_type", "market")

        new_decision = replace(decision, position_size_usd=min_notional)
        reason_parts = [
            f"{exchange_name} {order_type} min notional ${min_notional:,.2f}",
            f"margin ${required_margin:,.2f} @ {leverage}x",
        ]
        if reference_price:
            reason_parts.append(f"ref px {reference_price:.5g}")

        return self._modified(
            new_decision,
            field_name="position_size_usd",
            original_value=current_size,
            new_value=min_notional,
            reason="Bumped size to exchange minimum: " + ", ".join(reason_parts),
        )


class ExistingPositionStackingModifier(ModifierRule):
    OPEN_ACTIONS = {
        ExecutionAction.OPEN_LONG,
        ExecutionAction.OPEN_SHORT,
        ExecutionAction.OPEN_LONG_LIMIT,
        ExecutionAction.OPEN_SHORT_LIMIT,
    }
    DEFAULT_TIER_RANGES = {
        1: (0.70, 1.00),
        2: (0.35, 0.70),
        3: (0.15, 0.35),
    }
    DEFAULT_TIER = 2

    def __init__(
        self,
        tier_ranges: Optional[Dict[int, tuple[float, float]]] = None,
        default_range: Optional[tuple[float, float]] = None,
    ) -> None:
        self._tier_ranges = tier_ranges or {}
        self._default_range = default_range or self.DEFAULT_TIER_RANGES[self.DEFAULT_TIER]

    @property
    def name(self) -> str:
        return "existing_position_stacking"

    @property
    def description(self) -> str:
        return "Handles stacking on existing positions"

    def _get_validated_position_pct(self, tier: int, position_pct: Optional[float]) -> float:
        min_pct, max_pct = self._tier_ranges.get(tier, self._default_range)
        if position_pct is None:
            return min_pct
        if position_pct < min_pct or position_pct > max_pct:
            return min_pct
        return position_pct

    def modify(self, decision: ExecutionIdea, context: GuardContext) -> tuple:
        if decision.action not in self.OPEN_ACTIONS:
            return self._no_change(decision, "Not an OPEN action")

        open_positions = context.open_positions
        if not open_positions:
            return self._no_change(decision, "No existing positions")

        existing_position = None
        for pos in open_positions:
            if pos.get("symbol") == decision.symbol:
                existing_position = pos
                break

        if not existing_position:
            return self._no_change(decision, f"No existing position for {decision.symbol}")

        tier = decision.tier if decision.tier is not None else self.DEFAULT_TIER
        account_state = context.account_state
        if not account_state:
            return self._no_change(decision, "No account state available")

        account_value = account_state.get("account_value", 0)
        portfolio_exposure_pct = context.get_portfolio_exposure_pct()
        if account_value <= 0:
            return self._no_change(decision, "No account value available")

        max_available_margin = account_value * (portfolio_exposure_pct / 100.0)
        if max_available_margin <= 0:
            return self._no_change(decision, "No available margin")

        position_pct = decision.position_pct
        validated_pct = self._get_validated_position_pct(tier, position_pct)
        leverage = decision.leverage or 1
        max_tier_size = max_available_margin * validated_pct * leverage

        current_margin = existing_position.get("margin", 0)
        current_position_value = current_margin * leverage
        pct_used = (current_position_value / max_tier_size * 100) if max_tier_size > 0 else 0

        if pct_used >= 100:
            new_decision = replace(decision, action=ExecutionAction.HOLD)
            return self._modified(
                new_decision,
                field_name="action",
                original_value=decision.action.value,
                new_value="HOLD",
                reason=(
                    f"Position exists at {pct_used:.1f}% of tier {tier} max "
                    f"(${current_position_value:.2f}/${max_tier_size:.2f})"
                ),
            )

        remaining_room = max_tier_size - current_position_value
        original_size = decision.position_size_usd or 0
        adjusted_size = min(remaining_room, original_size)
        new_decision = replace(decision, position_size_usd=adjusted_size)

        return self._modified(
            new_decision,
            field_name="position_size_usd",
            original_value=original_size,
            new_value=adjusted_size,
            reason=(
                f"Stacking on existing position: {pct_used:.1f}% used, "
                f"adding ${adjusted_size:.2f} (room: ${remaining_room:.2f})"
            ),
        )


class StopLossROEModifier(ModifierRule):
    LONG_ACTIONS = {ExecutionAction.OPEN_LONG, ExecutionAction.OPEN_LONG_LIMIT}
    SHORT_ACTIONS = {ExecutionAction.OPEN_SHORT, ExecutionAction.OPEN_SHORT_LIMIT}
    OPEN_ACTIONS = LONG_ACTIONS | SHORT_ACTIONS

    def __init__(self, min_roe: float = 0.03, max_roe: float = 0.05) -> None:
        self._min_roe = min_roe
        self._max_roe = max_roe

    @property
    def name(self) -> str:
        return "stop_loss_roe"

    @property
    def description(self) -> str:
        return f"Validates stop_loss within ROE range ({self._min_roe*100:.0f}%-{self._max_roe*100:.0f}%)"

    def modify(self, decision: ExecutionIdea, context: GuardContext) -> tuple:
        if decision.action not in self.OPEN_ACTIONS:
            return self._no_change(decision, "Not an OPEN action")

        leverage = decision.leverage or 1
        if leverage <= 0:
            leverage = 1

        current_price = context.get_current_price(decision.symbol)
        if current_price is None or current_price <= 0:
            return self._no_change(decision, f"Could not fetch price for {decision.symbol}")

        llm_stop_loss = decision.stop_loss
        original_sl = llm_stop_loss
        is_long = decision.action in self.LONG_ACTIONS
        direction = "LONG" if is_long else "SHORT"

        if llm_stop_loss is not None and llm_stop_loss > 0:
            if is_long:
                llm_roe = (current_price - llm_stop_loss) / current_price * leverage
            else:
                llm_roe = (llm_stop_loss - current_price) / current_price * leverage

            if self._min_roe <= llm_roe <= self._max_roe:
                return self._no_change(
                    decision,
                    f"{direction} SL OK: {llm_stop_loss:.5g} (ROE: {llm_roe*100:.1f}%)",
                )

            if llm_roe < self._min_roe:
                clamped_roe = self._min_roe
                clamp_reason = "too tight"
            else:
                clamped_roe = self._max_roe
                clamp_reason = "too wide"
        else:
            clamped_roe = self._min_roe
            clamp_reason = "not specified"
            llm_roe = None

        if is_long:
            calculated_sl = current_price * (1 - (clamped_roe / leverage))
        else:
            calculated_sl = current_price * (1 + (clamped_roe / leverage))

        calculated_sl = float(f"{calculated_sl:.5g}")
        new_decision = replace(decision, stop_loss=calculated_sl)

        if llm_roe is not None:
            reason = (
                f"{direction} SL {clamp_reason}: {original_sl:.5g} ({llm_roe*100:.1f}%) → "
                f"{calculated_sl:.5g} ({clamped_roe*100:.1f}%)"
            )
        else:
            reason = f"{direction} SL {clamp_reason}: → {calculated_sl:.5g} ({clamped_roe*100:.1f}%, default)"

        return self._modified(
            new_decision,
            field_name="stop_loss",
            original_value=original_sl,
            new_value=calculated_sl,
            reason=reason,
        )


class TakeProfitROEModifier(ModifierRule):
    LONG_ACTIONS = {ExecutionAction.OPEN_LONG, ExecutionAction.OPEN_LONG_LIMIT}
    SHORT_ACTIONS = {ExecutionAction.OPEN_SHORT, ExecutionAction.OPEN_SHORT_LIMIT}
    OPEN_ACTIONS = LONG_ACTIONS | SHORT_ACTIONS

    def __init__(self, min_roe: float = 0.05, max_roe: float = 0.2) -> None:
        self._min_roe = min_roe
        self._max_roe = max_roe

    @property
    def name(self) -> str:
        return "take_profit_roe"

    @property
    def description(self) -> str:
        return (
            "Recalculates take_profit using live price and take_profit_roe "
            f"({self._min_roe*100:.0f}%-{self._max_roe*100:.0f}%)"
        )

    def modify(self, decision: ExecutionIdea, context: GuardContext) -> tuple:
        if decision.action not in self.OPEN_ACTIONS:
            return self._no_change(decision, "Not an OPEN action")

        take_profit_roe = decision.take_profit_roe
        if take_profit_roe is None:
            return self._no_change(decision, "No take_profit_roe specified")
        if take_profit_roe <= 0:
            return self._no_change(decision, f"Invalid take_profit_roe: {take_profit_roe}")

        clamp_reason = None
        if take_profit_roe < self._min_roe:
            clamped_roe = self._min_roe
            clamp_reason = "too small"
        elif take_profit_roe > self._max_roe:
            clamped_roe = self._max_roe
            clamp_reason = "too large"
        else:
            clamped_roe = take_profit_roe

        leverage = decision.leverage or 1
        if leverage <= 0:
            leverage = 1

        current_price = context.get_current_price(decision.symbol)
        if current_price is None or current_price <= 0:
            return self._no_change(decision, f"Could not fetch price for {decision.symbol}")

        original_tp = decision.take_profit
        if decision.action in self.LONG_ACTIONS:
            calculated_tp = current_price * (1 + (clamped_roe / leverage))
        else:
            calculated_tp = current_price * (1 - (clamped_roe / leverage))

        calculated_tp = float(f"{calculated_tp:.5g}")
        new_decision = replace(decision, take_profit=calculated_tp)
        direction = "LONG" if decision.action in self.LONG_ACTIONS else "SHORT"
        roe_detail = f"{clamped_roe*100:.1f}%"
        if clamp_reason:
            roe_detail = f"{take_profit_roe*100:.1f}% → {clamped_roe*100:.1f}% ({clamp_reason})"

        if original_tp is None or abs(calculated_tp - original_tp) > 0.0001:
            return self._modified(
                new_decision,
                field_name="take_profit",
                original_value=original_tp,
                new_value=calculated_tp,
                reason=(
                    f"{direction} TP: {original_tp} → {calculated_tp:.5g} "
                    f"(price: {current_price}, ROE: {roe_detail}, lev: {leverage}x)"
                ),
            )

        return self._no_change(
            new_decision,
            f"{direction} TP OK: {calculated_tp:.5g} (price: {current_price}, ROE: {roe_detail})",
        )


class ReduceToDustCloseModifier(ModifierRule):
    def __init__(self, dust_threshold_usd: float = 10.0) -> None:
        self._dust_threshold = dust_threshold_usd

    @property
    def name(self) -> str:
        return "reduce_dust_close"

    @property
    def description(self) -> str:
        return f"Converts REDUCE to CLOSE if remaining position < ${self._dust_threshold}"

    def modify(self, decision: ExecutionIdea, context: GuardContext) -> tuple:
        if decision.action != ExecutionAction.REDUCE:
            return self._no_change(decision, "Not a REDUCE action")

        reduce_pct = decision.reduce_pct
        if reduce_pct is None or reduce_pct <= 0:
            return self._no_change(decision, "No reduce_pct specified")

        open_positions = context.open_positions
        if not open_positions:
            return self._no_change(decision, "No open positions available")

        symbol = decision.symbol.upper() if decision.symbol else ""
        current_position = None
        for pos in open_positions:
            pos_symbol = pos.get("symbol", "").upper() if isinstance(pos, dict) else ""
            if pos_symbol == symbol:
                current_position = pos
                break

        if not current_position:
            return self._no_change(decision, f"No position found for {symbol}")

        position_value = abs(
            float(
                current_position.get("position_value_usd", 0)
                or current_position.get("notional_value", 0)
                or current_position.get("size_usd", 0)
            )
        )

        if position_value <= 0:
            return self._no_change(decision, "Could not determine position value")

        remaining_pct = (100 - reduce_pct) / 100
        remaining_value = position_value * remaining_pct

        if remaining_value < self._dust_threshold:
            new_decision = replace(decision, action=ExecutionAction.CLOSE, reduce_pct=None)
            return self._modified(
                new_decision,
                field_name="action",
                original_value="REDUCE",
                new_value="CLOSE",
                reason=(
                    f"REDUCE → CLOSE: remaining ${remaining_value:.2f} < "
                    f"dust threshold ${self._dust_threshold:.2f} "
                    f"(position: ${position_value:.2f}, reduce: {reduce_pct}%)"
                ),
            )

        return self._no_change(
            decision,
            f"REDUCE OK: remaining ${remaining_value:.2f} >= ${self._dust_threshold:.2f}",
        )


def create_default_guard(
    config: TradeGuardConfig,
    tradeable_symbols: Optional[Set[str]] = None,
) -> TradeGuard:
    guard = TradeGuard()

    guard.register_rule(ActionRequiredRule())
    guard.register_rule(SymbolRequiredRule())
    guard.register_rule(OpenActionFieldsRule())
    guard.register_rule(LimitOrderFieldsRule())
    guard.register_rule(ReduceActionFieldsRule())
    guard.register_rule(UpdateSLFieldsRule())
    guard.register_rule(UpdateTPFieldsRule())

    guard.register_rule(MinConfidenceRule(min_confidence=config.min_confidence))
    guard.register_rule(TradeableSymbolRule(tradeable_symbols=tradeable_symbols))

    leverage_tiers: Dict[int, Set[str]] = {}
    for tier in config.leverage_tiers:
        leverage_tiers[int(tier.leverage)] = {symbol.upper() for symbol in tier.symbols}

    tier_ranges: Dict[int, tuple[float, float]] = {}
    for tier_range in config.position_tier_ranges:
        tier_ranges[int(tier_range.tier)] = (float(tier_range.min_pct), float(tier_range.max_pct))

    default_range = tier_ranges.get(
        TierBasedPositionSizeModifier.DEFAULT_TIER,
        TierBasedPositionSizeModifier.DEFAULT_TIER_RANGES[TierBasedPositionSizeModifier.DEFAULT_TIER],
    )

    guard.register_modifier(
        MaxLeverageModifier(
            leverage_tiers=leverage_tiers,
            default_leverage=config.default_leverage,
        )
    )
    guard.register_modifier(
        ExistingPositionStackingModifier(tier_ranges=tier_ranges, default_range=default_range)
    )
    guard.register_modifier(
        TierBasedPositionSizeModifier(
            min_size_usd=config.min_position_size,
            tier_ranges=tier_ranges,
            default_range=default_range,
        )
    )
    guard.register_modifier(ExchangeMinimumOrderSizeModifier())
    guard.register_modifier(StopLossROEModifier(min_roe=config.sl_min_roe, max_roe=config.sl_max_roe))
    guard.register_modifier(TakeProfitROEModifier(min_roe=config.tp_min_roe, max_roe=config.tp_max_roe))
    guard.register_modifier(ReduceToDustCloseModifier(dust_threshold_usd=config.dust_threshold_usd))

    return guard
