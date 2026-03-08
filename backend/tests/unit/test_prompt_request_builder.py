from datetime import datetime, timezone

from app.application.automation.prompt_request_builder import build_prompt_request
from app.domain.ema_state_manager.models import EmaStateEvent, EmaStateTrigger, EmaTickerState


def _event(trigger: EmaStateTrigger, active=None, bb=None):
    return EmaStateEvent(
        symbol="BTC",
        trigger_reason=trigger,
        ticker_state=EmaTickerState(symbol="BTC"),
        resonance_count=2,
        active_intervals=active or [],
        direction_signal="LONG",
        bb_signal_intervals=bb or [],
        previous_resonance=0,
        previous_intervals=[],
        timestamp=datetime.now(timezone.utc),
    )


def test_bb_intervals_include_higher_timeframes():
    event = _event(EmaStateTrigger.BB_EXIT_WARNING, bb=["4h"])
    payload = build_prompt_request(event, ["2h", "4h", "8h", "1d"])
    assert payload["intervals"] == ["4h", "8h", "1d"]


def test_resonance_intervals_use_active_intervals():
    event = _event(EmaStateTrigger.NEW_RESONANCE, active=["2h", "4h"])
    payload = build_prompt_request(event, ["2h", "4h", "8h"])
    assert payload["intervals"] == ["2h", "4h", "8h"]


def test_entry_timing_15m_chart_appends_to_chart_requests_only():
    event = _event(EmaStateTrigger.NEW_RESONANCE, active=["2h", "4h"])
    payload = build_prompt_request(
        event,
        ["2h", "4h", "8h"],
        include_entry_timing_15m_chart=True,
    )
    chart_intervals = [item["interval"] for item in payload["chart_requests"]]
    assert payload["intervals"] == ["2h", "4h", "8h"]
    assert chart_intervals == ["2h", "4h", "8h", "15m"]


def test_entry_timing_15m_chart_not_added_for_position_management():
    event = _event(EmaStateTrigger.POSITION_MANAGEMENT, active=["2h", "4h"])
    payload = build_prompt_request(
        event,
        ["2h", "4h", "8h"],
        include_entry_timing_15m_chart=True,
    )
    chart_intervals = [item["interval"] for item in payload["chart_requests"]]
    assert payload["intervals"] == ["2h", "4h", "8h"]
    assert chart_intervals == ["2h", "4h", "8h"]


def test_entry_timing_15m_chart_is_deduped_when_already_present():
    event = _event(EmaStateTrigger.STRUCTURE_SHIFT, active=["15m", "2h"])
    payload = build_prompt_request(
        event,
        ["15m", "2h", "4h"],
        include_entry_timing_15m_chart=True,
    )
    chart_intervals = [item["interval"] for item in payload["chart_requests"]]
    assert payload["intervals"] == ["15m", "2h", "4h"]
    assert chart_intervals == ["15m", "2h", "4h"]
