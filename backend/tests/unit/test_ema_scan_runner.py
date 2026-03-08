import asyncio

import pytest

from app.application.ema_scanner.runner import (
    EmaScanAlreadyRunningError,
    EmaScanCancelledError,
    EmaScanRunner,
)
from app.domain.ema_scanner.models import EmaScannerConfig
from app.domain.ema_state_manager.models import DEFAULT_EMA_STATE_MANAGER_CONFIG


class StubConfigService:
    async def build_config(self, log_callback=None):
        return EmaScannerConfig(
            assets=["BTC"],
            timeframes=["1h"],
            ema_lengths=[20],
            tolerance_pct=0.2,
        )


class SlowScannerService:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def scan(self, config, log_callback=None, chart_store=None):
        self.started.set()
        await asyncio.sleep(60)
        return []


class StubResultsService:
    async def save_scan_results(self, results):
        return results


class StubStateService:
    async def process_signals(self, signals, monitored_assets, quote_asset, open_positions):
        return []

    async def get_config(self):
        return DEFAULT_EMA_STATE_MANAGER_CONFIG

    def get_all_states(self):
        return {}


class StubPortfolioSnapshot:
    def __init__(self) -> None:
        self.positions = []


class StubPortfolioService:
    async def get_portfolio_snapshot(self):
        return StubPortfolioSnapshot()


@pytest.mark.asyncio
async def test_runner_cancel_active_scan_emits_cancelled_log():
    scanner = SlowScannerService()
    runner = EmaScanRunner(
        config_service=StubConfigService(),
        scanner_service=scanner,
        results_service=StubResultsService(),
        state_service=StubStateService(),
        portfolio_service=StubPortfolioService(),
    )

    events: list[str] = []

    async def log_callback(event: str, data: dict | None = None):
        events.append(event)

    task = asyncio.create_task(runner.run_scan(log_callback=log_callback))
    await scanner.started.wait()

    assert runner.is_running() is True
    assert runner.cancel_active_scan() is True

    with pytest.raises(EmaScanCancelledError):
        await task
    assert "scan_cancelled" in events
    assert runner.is_running() is False


@pytest.mark.asyncio
async def test_runner_rejects_parallel_runs():
    scanner = SlowScannerService()
    runner = EmaScanRunner(
        config_service=StubConfigService(),
        scanner_service=scanner,
        results_service=StubResultsService(),
        state_service=StubStateService(),
        portfolio_service=StubPortfolioService(),
    )

    first = asyncio.create_task(runner.run_scan())
    await scanner.started.wait()

    with pytest.raises(EmaScanAlreadyRunningError):
        await runner.run_scan()

    runner.cancel_active_scan()
    with pytest.raises(EmaScanCancelledError):
        await first
