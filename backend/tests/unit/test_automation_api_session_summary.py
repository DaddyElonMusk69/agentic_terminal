from datetime import datetime, timezone

from app.api.v1.automation import _to_session_summary
from app.domain.automation_history.models import AutomationSessionRecord


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

