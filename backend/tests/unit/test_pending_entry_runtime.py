from __future__ import annotations

import asyncio
from types import MethodType

import pytest

from app.application.automation.runtime import AutomationRuntime, AutomationRuntimeConfig
from app.application.pending_entry.runtime import PendingEntryRuntime


class StubPendingEntryService:
    POLL_INTERVAL_SECONDS = 0.01

    def __init__(self) -> None:
        self.calls = 0

    async def poll_once(self) -> int:
        self.calls += 1
        return 0


class StubScheduler:
    def __init__(self, *args, session_id: str | None = None, **kwargs) -> None:  # noqa: ANN002,ANN003
        del args, kwargs
        self.session_id = session_id

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    def stats(self) -> dict:
        return {}


async def _idle_loop(self) -> None:  # noqa: ANN001
    await asyncio.Event().wait()


async def _wait_for(condition, *, timeout: float = 0.25) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if condition():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition was not met before timeout")


@pytest.mark.asyncio
async def test_pending_entry_runtime_polls_until_stopped():
    service = StubPendingEntryService()
    runtime = PendingEntryRuntime(service=service)

    await runtime.start()
    await _wait_for(lambda: service.calls >= 2)

    calls_before_stop = service.calls
    assert runtime.is_running() is True

    await runtime.stop()
    assert runtime.is_running() is False

    await asyncio.sleep(0.03)
    assert service.calls == calls_before_stop


@pytest.mark.asyncio
async def test_stopping_automation_does_not_stop_pending_entry_runtime(monkeypatch):
    pending_service = StubPendingEntryService()
    pending_runtime = PendingEntryRuntime(service=pending_service)
    await pending_runtime.start()
    await _wait_for(lambda: pending_service.calls >= 1)

    import app.application.automation.runtime as automation_runtime_module

    monkeypatch.setattr(automation_runtime_module, "AutomationScheduler", StubScheduler)
    monkeypatch.setattr(automation_runtime_module, "get_automation_pipeline_service", lambda: object())

    runtime = AutomationRuntime()
    runtime._run_prompt_loop = MethodType(_idle_loop, runtime)
    runtime._run_llm_loop = MethodType(_idle_loop, runtime)
    runtime._run_order_loop = MethodType(_idle_loop, runtime)
    runtime._run_outbox_loop = MethodType(_idle_loop, runtime)

    await runtime.start(AutomationRuntimeConfig(session_id="session-test"))
    assert len(runtime._tasks) == 4

    calls_before_stop = pending_service.calls
    await runtime.stop()
    assert pending_runtime.is_running() is True

    await _wait_for(lambda: pending_service.calls > calls_before_stop)
    await pending_runtime.stop()
