from types import SimpleNamespace

import pytest

from app.api.v1 import automation as automation_api
from app.domain.automation.models import AutomationConfig


class StubConfigService:
    async def update_config(self, **kwargs):
        return AutomationConfig(**kwargs)


class StubHistoryService:
    def __init__(self) -> None:
        self.started = []
        self.ended = []

    async def start_session(self, **kwargs):
        self.started.append(kwargs)
        return None

    async def end_session(self, **kwargs):
        self.ended.append(kwargs)
        return None


class StubRuntime:
    async def start(self, config):
        return {
            "is_running": True,
            "session_id": config.session_id,
            "execution_mode": config.execution_mode,
            "ema_interval_seconds": config.ema_interval_seconds,
            "quant_interval_seconds": config.quant_interval_seconds,
            "pending_entry_timeout_seconds": config.pending_entry_timeout_seconds,
            "max_positions": config.max_positions,
            "auto_add_enabled": config.auto_add_enabled,
            "auto_add_trigger_atr_multiple": config.auto_add_trigger_atr_multiple,
            "auto_add_tranche_margin_pct": config.auto_add_tranche_margin_pct,
            "auto_add_max_tranches": config.auto_add_max_tranches,
            "auto_add_protected_stop_roe": config.auto_add_protected_stop_roe,
            "provider": config.provider,
            "model": config.model,
            "reasoning_effort": config.reasoning_effort,
            "include_entry_timing_15m_chart": config.include_entry_timing_15m_chart,
            "use_all_monitored_interval_charts": config.use_all_monitored_interval_charts,
            "reverse_order_enabled": config.reverse_order_enabled,
            "vegas_prompt_configs": {
                "new_resonance": 81,
                "position_management": 74,
            },
            "started_at": "2026-05-08T00:00:00+00:00",
            "current_cycle": 0,
            "ema_cycles": 0,
            "quant_cycles": 0,
            "last_ema_cycle_at": None,
            "last_quant_cycle_at": None,
        }


class StubOutbox:
    def __init__(self) -> None:
        self.events = []

    async def enqueue_event(self, topic, payload):
        self.events.append((topic, payload))
        return SimpleNamespace(id="message-1")


class StubHub:
    def __init__(self) -> None:
        self.events = []

    async def emit_topic(self, topic, payload, request_id=None):
        self.events.append((topic, payload, request_id))


@pytest.mark.asyncio
async def test_start_automation_logs_runtime_prompt_config(monkeypatch):
    history_service = StubHistoryService()
    outbox = StubOutbox()
    hub = StubHub()

    async def load_prompt_template_names(prompt_configs):
        return {
            74: "Position Management",
            81: "Runtime New Resonance",
        }

    monkeypatch.setattr(automation_api, "get_automation_config_service", lambda: StubConfigService())
    monkeypatch.setattr(automation_api, "get_automation_history_service", lambda: history_service)
    monkeypatch.setattr(automation_api, "get_automation_runtime", lambda: StubRuntime())
    monkeypatch.setattr(automation_api, "get_outbox_service", lambda: outbox, raising=False)
    monkeypatch.setattr(automation_api, "hub", hub)
    monkeypatch.setattr(
        automation_api,
        "_load_prompt_template_names",
        load_prompt_template_names,
        raising=False,
    )

    payload = automation_api.AutomationStartRequest(
        execution_mode="production",
        ema_interval_seconds=60,
        quant_interval_seconds=60,
        pending_entry_timeout_seconds=900,
        max_positions=3,
        provider="codex",
        model="gpt-5.5",
        reasoning_effort="xhigh",
        vegas_prompt_configs={"new_resonance": 80},
    )

    await automation_api.start_automation(
        payload,
        SimpleNamespace(state=SimpleNamespace(request_id="req-1")),
    )

    assert outbox.events
    topic, prompt_log = outbox.events[-1]
    assert topic == "automation.prompt.config_selected"
    assert prompt_log["session_id"]
    assert prompt_log["execution_mode"] == "production"
    assert prompt_log["provider"] == "codex"
    assert prompt_log["model"] == "gpt-5.5"
    assert prompt_log["reasoning_effort"] == "xhigh"
    assert prompt_log["details"]["vegas_prompt_configs"] == {
        "new_resonance": 81,
        "position_management": 74,
    }
    assert prompt_log["details"]["resolved_prompt_configs"] == [
        {
            "key": "new_resonance",
            "template_id": 81,
            "template_name": "Runtime New Resonance",
            "status": "resolved",
        },
        {
            "key": "position_management",
            "template_id": 74,
            "template_name": "Position Management",
            "status": "resolved",
        },
    ]
    assert "new_resonance=#81 Runtime New Resonance" in prompt_log["message"]
    assert "position_management=#74 Position Management" in prompt_log["message"]
