from datetime import datetime, timezone

from app.api.v1.automation import _to_session_summary
from app.domain.automation_history.models import AutomationLogRecord, AutomationSessionRecord


def test_session_summary_exposes_prompt_versions_from_config_snapshot():
    session = AutomationSessionRecord(
        id="session-1",
        started_at=datetime(2026, 3, 25, 8, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 3, 25, 10, 0, tzinfo=timezone.utc),
        execution_mode="production",
        provider="codex",
        model="gpt-5.4",
        total_cycles=12,
        total_trades=4,
        total_pnl=24.5,
        prompt_count=18,
        config_snapshot={
            "vegas_prompt_configs": {
                "new_resonance": "26",
                "position_management": 29,
            }
        },
    )

    summary = _to_session_summary(session)

    assert summary.new_resonance_prompt_version == 26
    assert summary.position_management_prompt_version == 29


def test_session_summary_exposes_latest_ema_scanner_settings():
    session = AutomationSessionRecord(
        id="session-1",
        started_at=datetime(2026, 3, 25, 8, 0, tzinfo=timezone.utc),
        ended_at=None,
        execution_mode="production",
        provider="codex",
        model="gpt-5.4",
        total_cycles=2,
        total_trades=0,
        total_pnl=0.0,
        prompt_count=0,
        config_snapshot={
            "ema_interval_seconds": "45",
            "include_entry_timing_15m_chart": True,
            "use_all_monitored_interval_charts": "false",
        },
    )
    logs = [
        AutomationLogRecord(
            id=2,
            session_id="session-1",
            created_at=datetime(2026, 3, 25, 8, 2, tzinfo=timezone.utc),
            log_type="scanner",
            cycle_number=2,
            data={
                "event": "scan_config",
                "data": {
                    "assets_count": 3,
                    "timeframes_count": 2,
                    "ema_lines_count": 3,
                    "tolerance_pct": 0.15,
                    "assets": ["BTC", "ETH", "SOL"],
                    "timeframes": ["15m", "1h"],
                    "ema_lengths": [20, "50", 200],
                    "quote_asset": "USDT",
                    "monitored_intervals": ["5m", "15m", "1h"],
                },
            },
        ),
        AutomationLogRecord(
            id=1,
            session_id="session-1",
            created_at=datetime(2026, 3, 25, 8, 1, tzinfo=timezone.utc),
            log_type="scanner",
            cycle_number=1,
            data={
                "event": "scan_config",
                "data": {
                    "assets": ["BTC"],
                    "timeframes": ["5m"],
                    "ema_lengths": [9],
                    "quote_asset": "OLD",
                    "tolerance_pct": 0.5,
                },
            },
        ),
    ]

    summary = _to_session_summary(session, logs)

    assert summary.ema_scanner_settings == {
        "automation_interval_seconds": 45,
        "include_entry_timing_15m_chart": True,
        "use_all_monitored_interval_charts": False,
        "assets_count": 3,
        "timeframes_count": 2,
        "ema_lines_count": 3,
        "tolerance_pct": 0.15,
        "assets": ["BTC", "ETH", "SOL"],
        "timeframes": ["15m", "1h"],
        "ema_lengths": [20, 50, 200],
        "quote_asset": "USDT",
        "monitored_intervals": ["5m", "15m", "1h"],
    }


def test_session_summary_exposes_auto_add_settings_from_config_snapshot():
    session = AutomationSessionRecord(
        id="session-1",
        started_at=datetime(2026, 3, 25, 8, 0, tzinfo=timezone.utc),
        ended_at=None,
        execution_mode="production",
        provider="codex",
        model="gpt-5.4",
        total_cycles=1,
        total_trades=0,
        total_pnl=0.0,
        prompt_count=0,
        config_snapshot={
            "auto_add_enabled": True,
            "auto_add_trigger_atr_multiple": "1.25",
            "auto_add_tranche_margin_pct": 0.65,
            "auto_add_max_tranches": "4",
            "pending_entry_timeout_seconds": "1200",
        },
    )

    summary = _to_session_summary(session)

    assert summary.auto_add_settings == {
        "auto_add_enabled": True,
        "auto_add_trigger_atr_multiple": 1.25,
        "auto_add_tranche_margin_pct": 0.65,
        "auto_add_max_tranches": 4,
        "pending_entry_timeout_seconds": 1200,
    }
