from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Set

from app.domain.ema_scanner.models import EmaScannerSignal
from app.domain.ema_state_manager.models import (
    EmaStateEvent,
    EmaStateManagerConfig,
    EmaStateTrigger,
    EmaTickerPhase,
    EmaTickerState,
    IntervalSignalCounts,
    PositionSnapshot,
)


class EmaStateManager:
    """Tracks EMA/BB scan states and emits derived signal events."""

    def __init__(self) -> None:
        self._states: Dict[str, EmaTickerState] = {}

    def update(
        self,
        signals: Sequence[EmaScannerSignal],
        monitored_symbols: Sequence[str],
        config: EmaStateManagerConfig,
        open_positions: Sequence[PositionSnapshot] | None = None,
    ) -> List[EmaStateEvent]:
        now = datetime.now(timezone.utc)
        snapshot_symbols = {
            _normalize_symbol(symbol)
            for symbol in monitored_symbols
            if symbol and _normalize_symbol(symbol)
        }
        self._prune_states(snapshot_symbols)

        grouped_signals = _group_signals(signals, allowed_symbols=snapshot_symbols)
        grouped_positions = _group_positions(open_positions or [], allowed_symbols=snapshot_symbols)

        events: List[EmaStateEvent] = []
        for symbol in sorted(snapshot_symbols):
            event = self._update_symbol(
                symbol=symbol,
                signals=grouped_signals.get(symbol, []),
                position=grouped_positions.get(symbol),
                config=config,
                now=now,
            )
            if event is not None:
                events.append(event)

        return events

    def get_state(self, symbol: str) -> Optional[EmaTickerState]:
        return self._states.get(_normalize_symbol(symbol))

    def get_all_states(self) -> Dict[str, EmaTickerState]:
        return dict(self._states)

    def clear_state(self, symbol: str) -> None:
        normalized = _normalize_symbol(symbol)
        if normalized in self._states:
            del self._states[normalized]

    def clear_all_states(self) -> None:
        self._states.clear()

    def _prune_states(self, snapshot_symbols: Set[str]) -> None:
        for symbol in list(self._states.keys()):
            if symbol not in snapshot_symbols:
                del self._states[symbol]

    def _update_symbol(
        self,
        symbol: str,
        signals: Sequence[EmaScannerSignal],
        position: PositionSnapshot | None,
        config: EmaStateManagerConfig,
        now: datetime,
    ) -> Optional[EmaStateEvent]:
        state = self._states.get(symbol)
        if state is None:
            state = EmaTickerState(symbol=symbol)
            self._states[symbol] = state

        previous_resonance = state.resonance_count
        previous_intervals = set(state.active_intervals)

        ema_signals = [signal for signal in signals if signal.indicator == "EMA"]
        bb_signals = [signal for signal in signals if signal.indicator == "BB"]

        state.interval_states = _build_interval_states(
            state.interval_states,
            ema_signals=ema_signals,
            bb_signals=bb_signals,
            now=now,
        )

        active_intervals = {
            interval
            for interval, counts in state.interval_states.items()
            if counts.ema_signals > 0
        }

        state.last_updated = now

        if position is not None:
            return self._handle_position(
                state=state,
                position=position,
                bb_signals=bb_signals,
                config=config,
                now=now,
            )

        return self._handle_entry(
            state=state,
            ema_signals=ema_signals,
            bb_signals=bb_signals,
            active_intervals=active_intervals,
            previous_resonance=previous_resonance,
            previous_intervals=previous_intervals,
            config=config,
            now=now,
        )

    def _handle_position(
        self,
        state: EmaTickerState,
        position: PositionSnapshot,
        bb_signals: Sequence[EmaScannerSignal],
        config: EmaStateManagerConfig,
        now: datetime,
    ) -> Optional[EmaStateEvent]:
        state.phase = EmaTickerPhase.IN_POSITION
        state.resonance_count = 0
        state.active_intervals = set()
        state.bb_upper_touch_count = 0
        state.bb_lower_touch_count = 0
        state.bb_rejection_direction = None

        direction = _normalize_direction(position.direction)
        state.position_direction = direction
        state.position_entry_price = position.entry_price
        if state.position_opened_at is None:
            state.position_opened_at = now

        if state.last_position_prompt_at is None:
            state.last_position_prompt_at = now
            return None

        if not _cooldown_elapsed(
            state.last_position_prompt_at,
            config.position_check_interval_seconds,
            now,
        ):
            return None

        trigger_reason = EmaStateTrigger.NONE
        bb_signal_intervals: List[str] = []

        if _has_bb_exit_proximity(bb_signals, direction, config.bb_htf_min_interval_minutes):
            if config.emit_bb_exit_warning and _cooldown_elapsed(
                state.last_bb_exit_warning_prompt_at,
                config.bb_exit_warning_cooldown_seconds,
                now,
            ):
                trigger_reason = EmaStateTrigger.BB_EXIT_WARNING
                state.last_bb_exit_warning_prompt_at = now
                state.last_position_prompt_at = now
                bb_signal_intervals = _get_bb_exit_intervals(
                    bb_signals,
                    direction,
                    config.bb_htf_min_interval_minutes,
                )
            elif not config.emit_bb_exit_warning and config.emit_position_management:
                trigger_reason = EmaStateTrigger.POSITION_MANAGEMENT
                state.last_position_prompt_at = now
        elif config.emit_position_management:
            trigger_reason = EmaStateTrigger.POSITION_MANAGEMENT
            state.last_position_prompt_at = now

        if trigger_reason == EmaStateTrigger.NONE:
            return None

        state.last_trigger = trigger_reason
        state.last_trigger_at = now

        return EmaStateEvent(
            symbol=state.symbol,
            trigger_reason=trigger_reason,
            ticker_state=state,
            resonance_count=0,
            active_intervals=[],
            direction_signal=direction,
            bb_signal_intervals=bb_signal_intervals,
            previous_resonance=0,
            previous_intervals=[],
            timestamp=now,
        )

    def _handle_entry(
        self,
        state: EmaTickerState,
        ema_signals: Sequence[EmaScannerSignal],
        bb_signals: Sequence[EmaScannerSignal],
        active_intervals: Set[str],
        previous_resonance: int,
        previous_intervals: Set[str],
        config: EmaStateManagerConfig,
        now: datetime,
    ) -> Optional[EmaStateEvent]:
        resonance_count = len(active_intervals)
        state.resonance_count = resonance_count
        state.active_intervals = active_intervals
        state.phase = (
            EmaTickerPhase.ANALYZING
            if resonance_count >= config.min_resonance
            else EmaTickerPhase.IDLE
        )
        state.position_direction = None
        state.position_entry_price = None
        state.position_opened_at = None
        state.last_position_prompt_at = None
        state.last_bb_exit_warning_prompt_at = None

        trigger_reason = EmaStateTrigger.NONE
        bb_signal_intervals: List[str] = []
        direction_signal: Optional[str] = None

        if state.last_bb_rejection_prompt_at is not None and _cooldown_elapsed(
            state.last_bb_rejection_prompt_at,
            config.bb_rejection_cooldown_seconds,
            now,
        ):
            state.bb_upper_touch_count = 0
            state.bb_lower_touch_count = 0
            state.bb_rejection_direction = None
            state.last_bb_rejection_prompt_at = None

        bb_direction = _get_bb_rejection_direction(
            bb_signals,
            config.bb_htf_min_interval_minutes,
            state.bb_rejection_direction,
        )
        if bb_direction == "UPPER" and not config.emit_bb_rejection_upper:
            bb_direction = None
        elif bb_direction == "LOWER" and not config.emit_bb_rejection_lower:
            bb_direction = None

        if bb_direction:
            if state.bb_rejection_direction != bb_direction:
                state.bb_upper_touch_count = 0
                state.bb_lower_touch_count = 0
                state.bb_rejection_direction = bb_direction

            if bb_direction == "UPPER":
                state.bb_upper_touch_count += 1
                state.bb_lower_touch_count = 0
                touch_count = state.bb_upper_touch_count
            else:
                state.bb_lower_touch_count += 1
                state.bb_upper_touch_count = 0
                touch_count = state.bb_lower_touch_count
        else:
            state.bb_upper_touch_count = 0
            state.bb_lower_touch_count = 0
            state.bb_rejection_direction = None
            touch_count = 0

        if bb_direction and touch_count >= config.bb_rejection_min_touches:
            if _cooldown_elapsed(
                state.last_bb_rejection_prompt_at,
                config.bb_rejection_cooldown_seconds,
                now,
            ):
                trigger_reason = EmaStateTrigger.BB_REJECTION_ENTRY
                state.last_bb_rejection_prompt_at = now
                state.bb_upper_touch_count = 0
                state.bb_lower_touch_count = 0
                state.bb_rejection_direction = None
                bb_signal_intervals = _get_bb_rejection_intervals(
                    bb_signals,
                    bb_direction,
                    config.bb_htf_min_interval_minutes,
                )
                direction_signal = "SHORT" if bb_direction == "UPPER" else "LONG"

        if trigger_reason == EmaStateTrigger.NONE and resonance_count >= config.min_resonance:
            if _cooldown_elapsed(
                state.last_ema_resonance_prompt_at,
                config.ema_resonance_cooldown_seconds,
                now,
            ):
                if previous_resonance < config.min_resonance:
                    trigger_reason = EmaStateTrigger.NEW_RESONANCE
                elif resonance_count > previous_resonance:
                    trigger_reason = EmaStateTrigger.RESONANCE_INCREASE
                elif active_intervals != previous_intervals:
                    trigger_reason = EmaStateTrigger.STRUCTURE_SHIFT
                else:
                    trigger_reason = EmaStateTrigger.RESONANCE_REFRESH

        if trigger_reason == EmaStateTrigger.NEW_RESONANCE and not config.emit_new_resonance:
            trigger_reason = EmaStateTrigger.NONE
        elif (
            trigger_reason == EmaStateTrigger.RESONANCE_INCREASE
            and not config.emit_resonance_increase
        ):
            trigger_reason = EmaStateTrigger.NONE
        elif (
            trigger_reason == EmaStateTrigger.STRUCTURE_SHIFT
            and not config.emit_structure_shift
        ):
            trigger_reason = EmaStateTrigger.NONE
        elif (
            trigger_reason == EmaStateTrigger.RESONANCE_REFRESH
            and not config.emit_resonance_refresh
        ):
            trigger_reason = EmaStateTrigger.NONE

        if trigger_reason in (
            EmaStateTrigger.NEW_RESONANCE,
            EmaStateTrigger.RESONANCE_INCREASE,
            EmaStateTrigger.STRUCTURE_SHIFT,
            EmaStateTrigger.RESONANCE_REFRESH,
        ):
            state.last_ema_resonance_prompt_at = now

        if trigger_reason == EmaStateTrigger.NONE:
            return None

        if direction_signal is None:
            direction_signal = _infer_direction_from_ema(ema_signals)

        state.last_trigger = trigger_reason
        state.last_trigger_at = now

        return EmaStateEvent(
            symbol=state.symbol,
            trigger_reason=trigger_reason,
            ticker_state=state,
            resonance_count=resonance_count,
            active_intervals=sorted(active_intervals),
            direction_signal=direction_signal,
            bb_signal_intervals=bb_signal_intervals,
            previous_resonance=previous_resonance,
            previous_intervals=sorted(previous_intervals),
            timestamp=now,
        )


def _normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def _normalize_direction(direction: str | None) -> Optional[str]:
    if not direction:
        return None
    value = direction.strip().upper()
    if value == "BUY":
        return "LONG"
    if value == "SELL":
        return "SHORT"
    return value


def _group_signals(
    signals: Sequence[EmaScannerSignal],
    allowed_symbols: Set[str],
) -> Dict[str, List[EmaScannerSignal]]:
    grouped: Dict[str, List[EmaScannerSignal]] = {}
    for signal in signals:
        symbol = _normalize_symbol(signal.symbol)
        if not symbol or symbol not in allowed_symbols:
            continue
        grouped.setdefault(symbol, []).append(signal)
    return grouped


def _group_positions(
    positions: Sequence[PositionSnapshot],
    allowed_symbols: Set[str],
) -> Dict[str, PositionSnapshot]:
    grouped: Dict[str, PositionSnapshot] = {}
    for position in positions:
        symbol = _normalize_symbol(position.symbol)
        if not symbol or symbol not in allowed_symbols:
            continue
        direction = _normalize_direction(position.direction) or position.direction
        grouped[symbol] = PositionSnapshot(
            symbol=symbol,
            direction=direction,
            entry_price=position.entry_price,
        )
    return grouped


def _build_interval_states(
    existing: Dict[str, IntervalSignalCounts],
    ema_signals: Sequence[EmaScannerSignal],
    bb_signals: Sequence[EmaScannerSignal],
    now: datetime,
) -> Dict[str, IntervalSignalCounts]:
    intervals: Set[str] = set(existing.keys())
    intervals.update(signal.timeframe for signal in ema_signals if signal.timeframe)
    intervals.update(signal.timeframe for signal in bb_signals if signal.timeframe)

    states: Dict[str, IntervalSignalCounts] = {}
    for interval in intervals:
        ema_count = sum(1 for signal in ema_signals if signal.timeframe == interval)
        bb_upper_count = sum(
            1
            for signal in bb_signals
            if signal.timeframe == interval and "Upper" in signal.parameter
        )
        bb_lower_count = sum(
            1
            for signal in bb_signals
            if signal.timeframe == interval and "Lower" in signal.parameter
        )
        states[interval] = IntervalSignalCounts(
            interval=interval,
            ema_signals=ema_count,
            bb_upper_signals=bb_upper_count,
            bb_lower_signals=bb_lower_count,
            last_updated=now,
        )

    return states


def _interval_to_minutes(interval: str) -> Optional[int]:
    value = interval.strip().lower()
    if not value:
        return None

    number = ""
    suffix = ""
    for char in value:
        if char.isdigit():
            number += char
        else:
            suffix = value[len(number) :]
            break

    if not number or not suffix:
        return None

    try:
        amount = int(number)
    except ValueError:
        return None

    multipliers = {
        "m": 1,
        "h": 60,
        "d": 1440,
        "w": 10080,
    }
    if suffix not in multipliers:
        return None
    return amount * multipliers[suffix]


def _is_htf_interval(interval: str, min_minutes: int) -> bool:
    minutes = _interval_to_minutes(interval)
    if minutes is None:
        return False
    return minutes >= min_minutes


def _get_bb_rejection_direction(
    bb_signals: Sequence[EmaScannerSignal],
    min_minutes: int,
    previous_direction: Optional[str],
) -> Optional[str]:
    has_upper = any(
        "Upper" in signal.parameter
        and signal.timeframe
        and _is_htf_interval(signal.timeframe, min_minutes)
        for signal in bb_signals
    )
    has_lower = any(
        "Lower" in signal.parameter
        and signal.timeframe
        and _is_htf_interval(signal.timeframe, min_minutes)
        for signal in bb_signals
    )

    if has_upper and not has_lower:
        return "UPPER"
    if has_lower and not has_upper:
        return "LOWER"
    if has_upper and has_lower:
        return previous_direction if previous_direction in ("UPPER", "LOWER") else None
    return None


def _has_bb_exit_proximity(
    bb_signals: Sequence[EmaScannerSignal],
    direction: Optional[str],
    min_minutes: int,
) -> bool:
    if not direction:
        return False

    for signal in bb_signals:
        if not signal.timeframe or not _is_htf_interval(signal.timeframe, min_minutes):
            continue
        if direction == "LONG" and "Upper" in signal.parameter:
            return True
        if direction == "SHORT" and "Lower" in signal.parameter:
            return True
    return False


def _get_bb_exit_intervals(
    bb_signals: Sequence[EmaScannerSignal],
    direction: Optional[str],
    min_minutes: int,
) -> List[str]:
    if not direction:
        return []

    intervals: List[str] = []
    for signal in bb_signals:
        if not signal.timeframe or not _is_htf_interval(signal.timeframe, min_minutes):
            continue
        if direction == "LONG" and "Upper" in signal.parameter:
            intervals.append(signal.timeframe)
        if direction == "SHORT" and "Lower" in signal.parameter:
            intervals.append(signal.timeframe)
    return intervals


def _get_bb_rejection_intervals(
    bb_signals: Sequence[EmaScannerSignal],
    direction: Optional[str],
    min_minutes: int,
) -> List[str]:
    if direction not in ("UPPER", "LOWER"):
        return []

    target = "Upper" if direction == "UPPER" else "Lower"
    intervals: List[str] = []
    for signal in bb_signals:
        if not signal.timeframe or not _is_htf_interval(signal.timeframe, min_minutes):
            continue
        if target in signal.parameter:
            intervals.append(signal.timeframe)
    return intervals


def _infer_direction_from_ema(ema_signals: Sequence[EmaScannerSignal]) -> Optional[str]:
    for signal in ema_signals:
        if signal.price > signal.value:
            return "LONG"
        if signal.price < signal.value:
            return "SHORT"
    return None


def _cooldown_elapsed(
    last_prompt: Optional[datetime],
    cooldown_seconds: int,
    now: datetime,
) -> bool:
    if last_prompt is None:
        return True
    elapsed = (now - last_prompt).total_seconds()
    return elapsed >= cooldown_seconds
