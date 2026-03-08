from __future__ import annotations

from dataclasses import asdict
from typing import List, Optional, Sequence
from uuid import uuid4

from app.domain.ema_state_manager.models import EmaStateEvent
from app.application.automation.execution_mode import ExecutionMode, normalize_execution_mode
from app.domain.prompt_builder.models import ChartRequest


BB_TRIGGERS = {"bb_exit_warning", "bb_rejection_entry"}
RESONANCE_TRIGGERS = {
    "new_resonance",
    "resonance_increase",
    "structure_shift",
    "resonance_refresh",
}
POSITION_TRIGGER = "position_management"
ENTRY_TIMING_INTERVAL = "15m"
ENTRY_CHART_TRIGGERS = {
    "new_resonance",
    "resonance_increase",
    "structure_shift",
    "resonance_refresh",
    "bb_rejection_entry",
}


def build_prompt_request(
    event: EmaStateEvent,
    monitored_intervals: Sequence[str],
    template_id: Optional[int] = None,
    execution_mode: str | ExecutionMode | None = None,
    llm_model: Optional[str] = None,
    llm_provider: Optional[str] = None,
    include_entry_timing_15m_chart: bool = False,
    session_id: Optional[str] = None,
) -> dict:
    mode = normalize_execution_mode(
        execution_mode.value if isinstance(execution_mode, ExecutionMode) else execution_mode
    )
    trigger_reason = event.trigger_reason.value
    intervals = _select_intervals(event, monitored_intervals)
    primary_interval = _select_primary_interval(
        event.bb_signal_intervals or event.active_intervals or intervals
    )
    chart_intervals = _dedupe_preserve(intervals)
    if include_entry_timing_15m_chart and trigger_reason in ENTRY_CHART_TRIGGERS:
        if ENTRY_TIMING_INTERVAL not in chart_intervals:
            chart_intervals.append(ENTRY_TIMING_INTERVAL)
    chart_requests = [ChartRequest(interval=interval) for interval in chart_intervals]

    return {
        "request_id": str(uuid4()),
        "session_id": session_id,
        "execution_mode": mode.value,
        "template_id": template_id,
        "model": llm_model,
        "provider": llm_provider,
        "trigger_reason": trigger_reason,
        "tickers": [event.symbol],
        "intervals": intervals,
        "chart_requests": [asdict(item) for item in chart_requests],
        "template_context": {
            "ticker": event.symbol,
            "interval": primary_interval,
            "intervals": ", ".join(intervals),
            "active_intervals": ", ".join(event.active_intervals or []),
            "previous_intervals": ", ".join(event.previous_intervals or []),
            "trigger_reason": trigger_reason,
            "resonance_count": event.resonance_count,
            "direction": event.direction_signal,
        },
    }


def _select_intervals(event: EmaStateEvent, monitored_intervals: Sequence[str]) -> List[str]:
    trigger_reason = event.trigger_reason.value
    monitored = _dedupe_preserve(monitored_intervals)

    if trigger_reason == POSITION_TRIGGER:
        return monitored

    if trigger_reason in BB_TRIGGERS:
        bb_intervals = _dedupe_preserve(event.bb_signal_intervals)
        if not bb_intervals:
            return monitored
        combined: List[str] = []
        for interval in bb_intervals:
            combined.extend(_get_interval_and_higher(interval, monitored))
        return _dedupe_preserve(combined)

    if trigger_reason in RESONANCE_TRIGGERS:
        active_intervals = _dedupe_preserve(event.active_intervals)
        highest_interval = _highest_interval(active_intervals)
        if not highest_interval:
            return active_intervals
        next_higher = _get_next_higher_interval(highest_interval, monitored)
        if next_higher:
            return _dedupe_preserve([*active_intervals, next_higher])
        return active_intervals

    return _dedupe_preserve(event.active_intervals)


def _get_interval_and_higher(interval: str, monitored_intervals: Sequence[str]) -> List[str]:
    target_minutes = _timeframe_minutes(interval)
    if target_minutes is None:
        return [interval]

    higher: List[str] = []
    for candidate in monitored_intervals:
        minutes = _timeframe_minutes(candidate)
        if minutes is None:
            continue
        if minutes >= target_minutes:
            higher.append(candidate)
    return _dedupe_preserve(higher)


def _get_next_higher_interval(interval: str, monitored_intervals: Sequence[str]) -> Optional[str]:
    target_minutes = _timeframe_minutes(interval)
    if target_minutes is None:
        return None
    candidates: List[tuple[int, str]] = []
    for candidate in monitored_intervals:
        minutes = _timeframe_minutes(candidate)
        if minutes is None:
            continue
        if minutes > target_minutes:
            candidates.append((minutes, candidate))
    if not candidates:
        return None
    min_minutes = min(item[0] for item in candidates)
    for candidate in monitored_intervals:
        if _timeframe_minutes(candidate) == min_minutes:
            return candidate
    return None


def _timeframe_minutes(timeframe: str) -> Optional[int]:
    if not timeframe:
        return None
    value = timeframe.strip().lower()
    if value.endswith("m") and value[:-1].isdigit():
        return int(value[:-1])
    if value.endswith("h") and value[:-1].isdigit():
        return int(value[:-1]) * 60
    if value.endswith("d") and value[:-1].isdigit():
        return int(value[:-1]) * 1440
    return None


def _select_primary_interval(intervals: Sequence[str]) -> str:
    best: Optional[str] = None
    best_minutes: Optional[int] = None
    for interval in intervals:
        minutes = _timeframe_minutes(interval)
        if minutes is None:
            if best is None:
                best = interval
            continue
        if best_minutes is None or minutes > best_minutes:
            best = interval
            best_minutes = minutes
    return best or ""


def _highest_interval(intervals: Sequence[str]) -> Optional[str]:
    best: Optional[str] = None
    best_minutes: Optional[int] = None
    for interval in intervals:
        minutes = _timeframe_minutes(interval)
        if minutes is None:
            continue
        if best_minutes is None or minutes > best_minutes:
            best_minutes = minutes
            best = interval
    return best


def _dedupe_preserve(values: Sequence[str]) -> List[str]:
    seen = set()
    output: List[str] = []
    for value in values:
        item = str(value)
        if item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output
