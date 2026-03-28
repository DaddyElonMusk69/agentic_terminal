from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, List, Optional, Set

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
from app.domain.trade_guard.models import DEFAULT_TRADE_GUARD_CONFIG, TradeGuardConfig


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
        return "Validates UPDATE_SL action has valid new_stop_loss or stop_loss_roe"

    def check(self, context: GuardContext) -> RuleResult:
        decision = context.decision
        if decision.action != ExecutionAction.UPDATE_SL:
            return self._pass("Not an UPDATE_SL action")

        if decision.new_stop_loss is not None:
            if decision.new_stop_loss <= 0:
                return self._fail(f"new_stop_loss must be > 0, got {decision.new_stop_loss}")
            return self._pass()

        if decision.stop_loss_roe is None:
            return self._fail("UPDATE_SL action requires new_stop_loss or stop_loss_roe")

        position = _resolve_open_position(context.open_positions, decision.symbol)
        if position is None:
            return self._fail("UPDATE_SL with stop_loss_roe requires an open position")

        entry_price = _safe_float(position.get("entry_price"))
        if entry_price is None or entry_price <= 0:
            return self._fail("UPDATE_SL with stop_loss_roe requires position entry_price")

        leverage = _resolve_position_leverage(position)
        if leverage is None or leverage <= 0:
            return self._fail("UPDATE_SL with stop_loss_roe requires position leverage")

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
        return "Validates UPDATE_TP action has valid new_take_profit or take_profit_roe"

    def check(self, context: GuardContext) -> RuleResult:
        decision = context.decision
        if decision.action != ExecutionAction.UPDATE_TP:
            return self._pass("Not an UPDATE_TP action")

        if decision.new_take_profit is not None:
            if decision.new_take_profit <= 0:
                return self._fail(f"new_take_profit must be > 0, got {decision.new_take_profit}")
            return self._pass()

        if decision.take_profit_roe is None:
            return self._fail("UPDATE_TP action requires new_take_profit or take_profit_roe")
        if decision.take_profit_roe <= 0:
            return self._fail(f"take_profit_roe must be > 0, got {decision.take_profit_roe}")

        position = _resolve_open_position(context.open_positions, decision.symbol)
        if position is None:
            return self._fail("UPDATE_TP with take_profit_roe requires an open position")

        entry_price = _safe_float(position.get("entry_price"))
        if entry_price is None or entry_price <= 0:
            return self._fail("UPDATE_TP with take_profit_roe requires position entry_price")

        leverage = _resolve_position_leverage(position)
        if leverage is None or leverage <= 0:
            return self._fail("UPDATE_TP with take_profit_roe requires position leverage")

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
    _MIN_NOTIONAL_BUFFER_USD = 1.0

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
        min_notional_with_buffer = min_notional + self._MIN_NOTIONAL_BUFFER_USD

        if current_size >= min_notional_with_buffer:
            return self._no_change(
                decision,
                "Meets exchange minimum notional + buffer: "
                f"${current_size:,.2f} >= ${min_notional_with_buffer:,.2f}",
            )

        leverage = decision.leverage or 1
        required_margin = (
            min_notional_with_buffer / leverage if leverage > 0 else min_notional_with_buffer
        )
        exchange_name = market_data.get("exchange_name", "exchange")
        order_type = market_data.get("order_type", "market")

        new_decision = replace(decision, position_size_usd=min_notional_with_buffer)
        reason_parts = [
            f"{exchange_name} {order_type} min notional ${min_notional_with_buffer:,.2f}",
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
            "Recalculates take_profit using live price with precedence "
            "configured tp_min_roe -> model take_profit_roe -> default tp_min_roe "
            f"(max {self._max_roe*100:.0f}%)"
        )

    def modify(self, decision: ExecutionIdea, context: GuardContext) -> tuple:
        if decision.action not in self.OPEN_ACTIONS:
            return self._no_change(decision, "Not an OPEN action")

        leverage = decision.leverage or 1
        if leverage <= 0:
            leverage = 1

        current_price = context.get_current_price(decision.symbol)
        if current_price is None or current_price <= 0:
            return self._no_change(decision, f"Could not fetch price for {decision.symbol}")

        original_tp = decision.take_profit
        configured_min_roe = self._min_roe if self._min_roe > 0 else None
        default_min_roe = DEFAULT_TRADE_GUARD_CONFIG.tp_min_roe
        max_roe = self._max_roe if self._max_roe > 0 else DEFAULT_TRADE_GUARD_CONFIG.tp_max_roe
        fallback_min_roe = configured_min_roe if configured_min_roe is not None else default_min_roe
        if max_roe < fallback_min_roe:
            max_roe = fallback_min_roe

        model_take_profit_roe = decision.take_profit_roe
        invalid_roe = None
        if model_take_profit_roe is not None and model_take_profit_roe <= 0:
            invalid_roe = model_take_profit_roe
            model_take_profit_roe = None

        clamp_reason = None
        llm_roe = None
        direction = "LONG" if decision.action in self.LONG_ACTIONS else "SHORT"
        is_long = decision.action in self.LONG_ACTIONS

        if configured_min_roe is not None:
            clamped_roe = fallback_min_roe
            clamp_reason = "configured tp_min_roe"
        elif model_take_profit_roe is not None:
            llm_roe = model_take_profit_roe
            if model_take_profit_roe < fallback_min_roe:
                clamped_roe = fallback_min_roe
                clamp_reason = "too small"
            elif model_take_profit_roe > max_roe:
                clamped_roe = max_roe
                clamp_reason = "too large"
            else:
                clamped_roe = model_take_profit_roe
        else:
            clamped_roe = default_min_roe
            if invalid_roe is not None:
                clamp_reason = f"invalid take_profit_roe: {invalid_roe}"
            else:
                clamp_reason = "default tp_min_roe"

        if is_long:
            calculated_tp = current_price * (1 + (clamped_roe / leverage))
        else:
            calculated_tp = current_price * (1 - (clamped_roe / leverage))

        calculated_tp = float(f"{calculated_tp:.5g}")
        new_decision = replace(decision, take_profit=calculated_tp)
        roe_detail = f"{clamped_roe*100:.1f}%"
        if llm_roe is not None and clamp_reason:
            roe_detail = f"{llm_roe*100:.1f}% → {clamped_roe*100:.1f}% ({clamp_reason})"
        elif clamp_reason and llm_roe is None:
            roe_detail = f"{clamped_roe*100:.1f}% ({clamp_reason})"

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


class UpdateStopLossROEModifier(ModifierRule):
    @property
    def name(self) -> str:
        return "update_stop_loss_roe"

    @property
    def description(self) -> str:
        return "Converts UPDATE_SL stop_loss_roe into a concrete new_stop_loss price"

    def modify(self, decision: ExecutionIdea, context: GuardContext) -> tuple:
        if decision.action != ExecutionAction.UPDATE_SL:
            return self._no_change(decision, "Not an UPDATE_SL action")

        if decision.new_stop_loss is not None:
            return self._no_change(decision, "new_stop_loss already provided")

        target_roe = decision.stop_loss_roe
        if target_roe is None:
            return self._no_change(decision, "No stop_loss_roe provided")

        position = _resolve_open_position(context.open_positions, decision.symbol)
        if position is None:
            return self._no_change(decision, "No open position available")

        direction = _resolve_position_side(context.open_positions, decision.symbol)
        entry_price = _safe_float(position.get("entry_price"))
        leverage = _resolve_position_leverage(position)

        if direction not in ("long", "short"):
            return self._no_change(decision, "Could not resolve position direction")
        if entry_price is None or entry_price <= 0:
            return self._no_change(decision, "No valid entry_price available")
        if leverage is None or leverage <= 0:
            return self._no_change(decision, "No valid leverage available")

        new_stop_loss = _calculate_stop_loss_from_roe(
            target_roe=target_roe,
            entry_price=entry_price,
            leverage=leverage,
            direction=direction,
        )
        if new_stop_loss is None or new_stop_loss <= 0:
            return self._no_change(decision, "Failed to calculate new_stop_loss from stop_loss_roe")

        updated_decision = replace(decision, new_stop_loss=new_stop_loss)
        return self._modified(
            updated_decision,
            field_name="new_stop_loss",
            original_value=None,
            new_value=new_stop_loss,
            reason=(
                f"Converted stop_loss_roe {target_roe*100:.2f}% to stop {new_stop_loss:.5g} "
                f"(entry: {entry_price}, lev: {leverage}x, side: {direction})"
            ),
        )


class UpdateTakeProfitROEModifier(ModifierRule):
    @property
    def name(self) -> str:
        return "update_take_profit_roe"

    @property
    def description(self) -> str:
        return "Converts UPDATE_TP take_profit_roe into a concrete new_take_profit price"

    def modify(self, decision: ExecutionIdea, context: GuardContext) -> tuple:
        if decision.action != ExecutionAction.UPDATE_TP:
            return self._no_change(decision, "Not an UPDATE_TP action")

        if decision.new_take_profit is not None:
            return self._no_change(decision, "new_take_profit already provided")

        target_roe = decision.take_profit_roe
        if target_roe is None:
            return self._no_change(decision, "No take_profit_roe provided")

        position = _resolve_open_position(context.open_positions, decision.symbol)
        if position is None:
            return self._no_change(decision, "No open position available")

        direction = _resolve_position_side(context.open_positions, decision.symbol)
        entry_price = _safe_float(position.get("entry_price"))
        leverage = _resolve_position_leverage(position)

        if direction not in ("long", "short"):
            return self._no_change(decision, "Could not resolve position direction")
        if entry_price is None or entry_price <= 0:
            return self._no_change(decision, "No valid entry_price available")
        if leverage is None or leverage <= 0:
            return self._no_change(decision, "No valid leverage available")

        new_take_profit = _calculate_take_profit_from_roe(
            target_roe=target_roe,
            entry_price=entry_price,
            leverage=leverage,
            direction=direction,
        )
        if new_take_profit is None or new_take_profit <= 0:
            return self._no_change(decision, "Failed to calculate new_take_profit from take_profit_roe")

        updated_decision = replace(decision, new_take_profit=new_take_profit)
        return self._modified(
            updated_decision,
            field_name="new_take_profit",
            original_value=None,
            new_value=new_take_profit,
            reason=(
                f"Converted take_profit_roe {target_roe*100:.2f}% to target {new_take_profit:.5g} "
                f"(entry: {entry_price}, lev: {leverage}x, side: {direction})"
            ),
        )


class TightenStopLossModifier(ModifierRule):
    @property
    def name(self) -> str:
        return "tighten_stop_loss"

    @property
    def description(self) -> str:
        return "Blocks UPDATE_SL if new stop loss is wider than existing"

    def modify(self, decision: ExecutionIdea, context: GuardContext) -> tuple:
        if decision.action != ExecutionAction.UPDATE_SL:
            return self._no_change(decision, "Not an UPDATE_SL action")

        new_sl = decision.new_stop_loss
        if new_sl is None or new_sl <= 0:
            return self._no_change(decision, "No valid new_stop_loss")

        previous_sl = _resolve_previous_stop_loss(decision, context)
        if previous_sl is None or previous_sl <= 0:
            return self._no_change(decision, "No previous stop loss available")

        direction = _resolve_position_side(context.open_positions, decision.symbol)
        current_price = context.get_current_price(decision.symbol)

        if _is_stop_loss_wider(new_sl, previous_sl, direction, current_price):
            new_decision = replace(decision, action=ExecutionAction.HOLD, new_stop_loss=None)
            return self._modified(
                new_decision,
                field_name="action",
                original_value=decision.action.value,
                new_value="HOLD",
                reason=f"UPDATE_SL blocked: {new_sl:.5g} wider than {previous_sl:.5g}",
            )

        return self._no_change(decision, "SL is tighter or unchanged")


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
    guard.register_modifier(UpdateStopLossROEModifier())
    guard.register_modifier(UpdateTakeProfitROEModifier())
    guard.register_modifier(TightenStopLossModifier())
    guard.register_modifier(ReduceToDustCloseModifier(dust_threshold_usd=config.dust_threshold_usd))

    return guard


def _resolve_previous_stop_loss(
    decision: ExecutionIdea,
    context: GuardContext,
) -> Optional[float]:
    symbol = decision.symbol
    direction = _resolve_position_side(context.open_positions, symbol)
    current_price = context.get_current_price(symbol)

    stop_prices = _extract_stop_prices(context.open_orders or [], symbol)
    if stop_prices:
        return _select_stop_price(stop_prices, direction, current_price)

    fallback = decision.stop_loss
    if fallback is not None and fallback > 0:
        return float(fallback)
    return None


def _resolve_open_position(open_positions: Optional[list], symbol: str) -> Optional[dict]:
    if not open_positions or not symbol:
        return None
    target = _normalize_symbol(symbol)
    for pos in open_positions:
        if not isinstance(pos, dict):
            continue
        pos_symbol = _normalize_symbol(pos.get("symbol"))
        if target and pos_symbol and pos_symbol != target:
            continue
        return pos
    return None


def _resolve_position_side(open_positions: Optional[list], symbol: str) -> Optional[str]:
    position = _resolve_open_position(open_positions, symbol)
    if not position:
        return None
    side = str(position.get("direction") or position.get("side") or "").lower()
    if side in ("long", "short"):
        return side
    size = _safe_float(position.get("size"))
    if size is not None:
        if size > 0:
            return "long"
        if size < 0:
            return "short"
    return None


def _resolve_position_leverage(position: dict) -> Optional[float]:
    leverage = _safe_float(position.get("leverage"))
    if leverage is not None and leverage > 0:
        return leverage

    margin = _safe_float(position.get("margin"))
    entry_price = _safe_float(position.get("entry_price"))
    size = _safe_float(position.get("size"))
    if margin is None or margin <= 0 or entry_price is None or entry_price <= 0 or size is None:
        return None

    notional = abs(size) * entry_price
    if notional <= 0:
        return None
    return notional / margin


def _calculate_stop_loss_from_roe(
    *,
    target_roe: float,
    entry_price: float,
    leverage: float,
    direction: str,
) -> Optional[float]:
    if leverage <= 0 or entry_price <= 0 or direction not in ("long", "short"):
        return None
    if direction == "long":
        stop_price = entry_price * (1 + (target_roe / leverage))
    else:
        stop_price = entry_price * (1 - (target_roe / leverage))
    return float(f"{stop_price:.5g}")


def _calculate_take_profit_from_roe(
    *,
    target_roe: float,
    entry_price: float,
    leverage: float,
    direction: str,
) -> Optional[float]:
    if leverage <= 0 or entry_price <= 0 or direction not in ("long", "short"):
        return None
    if direction == "long":
        take_profit = entry_price * (1 + (target_roe / leverage))
    else:
        take_profit = entry_price * (1 - (target_roe / leverage))
    return float(f"{take_profit:.5g}")


def _extract_stop_prices(orders: list, symbol: str) -> List[float]:
    prices: List[float] = []
    target = _normalize_symbol(symbol)
    for order in orders:
        if not isinstance(order, dict):
            continue
        info = order.get("info") if isinstance(order.get("info"), dict) else {}
        order_symbol = _normalize_symbol(order.get("symbol") or info.get("symbol"))
        if target and order_symbol and order_symbol != target:
            continue

        order_type = str(
            order.get("type")
            or order.get("orderType")
            or info.get("type")
            or info.get("orderType")
            or ""
        ).lower()

        stop_price = _safe_float(
            order.get("stopPrice")
            or order.get("triggerPrice")
            or order.get("triggerPx")
            or info.get("stopPrice")
            or info.get("triggerPrice")
            or info.get("triggerPx")
        )
        if stop_price is None:
            continue

        if "take" in order_type and "stop" not in order_type:
            continue

        prices.append(stop_price)

    return prices


def _select_stop_price(
    stop_prices: List[float],
    direction: Optional[str],
    current_price: Optional[float],
) -> Optional[float]:
    if not stop_prices:
        return None
    if direction == "long":
        return max(stop_prices)
    if direction == "short":
        return min(stop_prices)
    if current_price is not None:
        return min(stop_prices, key=lambda price: abs(current_price - price))
    return stop_prices[0]


def _is_stop_loss_wider(
    new_sl: float,
    previous_sl: float,
    direction: Optional[str],
    current_price: Optional[float],
) -> bool:
    if direction == "long":
        return new_sl < previous_sl
    if direction == "short":
        return new_sl > previous_sl
    if current_price is not None:
        return abs(current_price - new_sl) > abs(current_price - previous_sl)
    return False


def _normalize_symbol(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    symbol = value.strip().upper()
    if not symbol:
        return ""
    if ":" in symbol:
        symbol = symbol.split(":", 1)[0]
    if "/" in symbol:
        return symbol.split("/", 1)[0]

    for quote in _KNOWN_QUOTES:
        if symbol.endswith(quote) and len(symbol) > len(quote):
            return symbol[: -len(quote)]

    return symbol


_KNOWN_QUOTES = (
    "USDT",
    "USDC",
    "USD",
    "BUSD",
    "TUSD",
    "FDUSD",
    "USDP",
    "DAI",
)


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
