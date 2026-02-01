from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional

from app.domain.ema_state_manager.models import EmaStateManagerConfig, EmaTickerPhase, EmaTickerState


def build_vegas_state_payload(
    states: Dict[str, EmaTickerState],
    config: EmaStateManagerConfig,
) -> dict:
    now = datetime.now(timezone.utc)
    payload = [_serialize_state(state, config, now) for state in states.values()]
    payload.sort(key=lambda item: item["ticker"])
    return {"states": payload}


def _serialize_state(
    state: EmaTickerState,
    config: EmaStateManagerConfig,
    now: datetime,
) -> dict:
    phase = state.phase
    if phase == EmaTickerPhase.IN_POSITION:
        state_label = "POSITION_ACTIVE"
    elif phase == EmaTickerPhase.ANALYZING:
        state_label = "IN_TUNNEL"
    else:
        state_label = "IDLE"

    active_intervals = sorted(state.active_intervals)
    interval_crossings: dict = {}
    for interval, counts in state.interval_states.items():
        if (
            counts.ema_signals <= 0
            and counts.bb_upper_signals <= 0
            and counts.bb_lower_signals <= 0
            and interval not in active_intervals
        ):
            continue
        interval_crossings[interval] = {
            "in_tunnel": counts.ema_signals > 0,
            "bb_upper": counts.bb_upper_signals > 0,
            "bb_lower": counts.bb_lower_signals > 0,
        }

    timers = _build_timers(state, config, now)

    return {
        "ticker": state.symbol,
        "state": state_label,
        "resonance_count": state.resonance_count,
        "active_intervals": active_intervals,
        "interval_crossings": interval_crossings,
        "entry_price": state.position_entry_price,
        "entry_time": state.position_opened_at.isoformat() if state.position_opened_at else None,
        "direction": state.position_direction,
        "bb_rejection_direction": state.bb_rejection_direction,
        "timers": timers or None,
    }


def _build_timers(
    state: EmaTickerState,
    config: EmaStateManagerConfig,
    now: datetime,
) -> dict:
    timers: dict = {}

    if state.phase == EmaTickerPhase.IN_POSITION:
        remaining = _remaining_seconds(state.last_position_prompt_at, config.position_check_interval_seconds, now)
        if remaining is not None:
            timers["position_mgmt_remaining_sec"] = remaining
            timers["position_mgmt_total_sec"] = config.position_check_interval_seconds

    ema_remaining = _remaining_seconds(
        state.last_ema_resonance_prompt_at,
        config.ema_resonance_cooldown_seconds,
        now,
    )
    if ema_remaining is not None:
        timers["ema_resonance_remaining_sec"] = ema_remaining
        timers["ema_resonance_total_sec"] = config.ema_resonance_cooldown_seconds

    has_bb_rejection_activity = (
        state.last_bb_rejection_prompt_at is not None
        or state.bb_rejection_direction is not None
        or state.bb_upper_touch_count > 0
        or state.bb_lower_touch_count > 0
    )
    if has_bb_rejection_activity:
        if state.last_bb_rejection_prompt_at is not None:
            bb_rejection_remaining = _remaining_seconds(
                state.last_bb_rejection_prompt_at,
                config.bb_rejection_cooldown_seconds,
                now,
            )
        else:
            bb_rejection_remaining = 0
        if bb_rejection_remaining is None:
            bb_rejection_remaining = 0
        timers["bb_rejection_remaining_sec"] = bb_rejection_remaining
        timers["bb_rejection_total_sec"] = config.bb_rejection_cooldown_seconds

    bb_exit_remaining = _remaining_seconds(
        state.last_bb_exit_warning_prompt_at,
        config.bb_exit_warning_cooldown_seconds,
        now,
    )
    if bb_exit_remaining is not None:
        timers["bb_exit_warning_remaining_sec"] = bb_exit_remaining
        timers["bb_exit_warning_total_sec"] = config.bb_exit_warning_cooldown_seconds

    touch_direction = state.bb_rejection_direction
    if touch_direction:
        if touch_direction == "UPPER":
            touch_count = state.bb_upper_touch_count
        else:
            touch_count = state.bb_lower_touch_count
        timers["bb_touch_count"] = touch_count
        timers["bb_touch_direction"] = touch_direction
        timers["bb_touch_required"] = config.bb_rejection_min_touches

    return timers


def _remaining_seconds(
    last_at: Optional[datetime],
    cooldown_seconds: int,
    now: datetime,
) -> Optional[int]:
    if last_at is None:
        return None
    if cooldown_seconds <= 0:
        return None
    elapsed = (now - last_at).total_seconds()
    return max(0, int(cooldown_seconds - elapsed))
