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


def test_entry_timing_15m_chart_appends_to_chart_requests():
    event = _event(EmaStateTrigger.NEW_RESONANCE, active=["2h", "4h"])
    payload = build_prompt_request(
        event,
        ["2h", "4h", "8h"],
        include_entry_timing_15m_chart=True,
    )
    chart_intervals = [item["interval"] for item in payload["chart_requests"]]
    assert payload["intervals"] == ["2h", "4h", "8h"]
    assert chart_intervals == ["2h", "4h", "8h", "15m"]


def test_entry_timing_15m_chart_added_for_position_management():
    event = _event(EmaStateTrigger.POSITION_MANAGEMENT, active=["2h", "4h"])
    payload = build_prompt_request(
        event,
        ["2h", "4h", "8h"],
        include_entry_timing_15m_chart=True,
    )
    chart_intervals = [item["interval"] for item in payload["chart_requests"]]
    assert payload["intervals"] == ["2h", "4h", "8h"]
    assert chart_intervals == ["2h", "4h", "8h", "15m"]


def test_position_management_template_context_includes_position_fields():
    event = _event(EmaStateTrigger.POSITION_MANAGEMENT, active=["2h", "4h"])
    event.ticker_state.position_direction = "LONG"
    event.ticker_state.position_entry_price = 123.45
    event.ticker_state.position_opened_at = datetime(2024, 9, 1, 8, 0, tzinfo=timezone.utc)
    event.timestamp = datetime(2024, 9, 1, 10, 30, tzinfo=timezone.utc)

    payload = build_prompt_request(event, ["2h", "4h", "8h"])

    assert payload["template_context"]["position_side"] == "LONG"
    assert payload["template_context"]["entry_price"] == 123.45
    assert payload["template_context"]["duration"] == "2h30m"


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


def test_all_monitored_interval_charts_expand_chart_requests_only():
    event = _event(EmaStateTrigger.NEW_RESONANCE, active=["2h", "4h"])
    payload = build_prompt_request(
        event,
        ["30m", "1h", "2h", "4h", "8h"],
        use_all_monitored_interval_charts=True,
    )
    chart_intervals = [item["interval"] for item in payload["chart_requests"]]
    assert payload["intervals"] == ["2h", "4h", "8h"]
    assert chart_intervals == ["30m", "1h", "2h", "4h", "8h"]


def test_all_monitored_interval_charts_still_dedupes_entry_timing_chart():
    event = _event(EmaStateTrigger.NEW_RESONANCE, active=["2h", "4h"])
    payload = build_prompt_request(
        event,
        ["15m", "30m", "1h", "2h", "4h", "8h"],
        include_entry_timing_15m_chart=True,
        use_all_monitored_interval_charts=True,
    )
    chart_intervals = [item["interval"] for item in payload["chart_requests"]]
    assert payload["intervals"] == ["2h", "4h", "8h"]
    assert chart_intervals == ["15m", "30m", "1h", "2h", "4h", "8h"]
