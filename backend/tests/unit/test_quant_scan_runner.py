import asyncio

import pytest

from app.application.quant_scanner.runner import (
    QuantScanAlreadyRunningError,
    QuantScanCancelledError,
    QuantScanRunner,
)
from app.domain.quant_scanner.models import QuantScannerConfig


class StubConfigService:
    async def build_config(self):
        return QuantScannerConfig(
            assets=["BTC"],
            timeframes=["1h"],
            quote_asset="USDT",
        )


class SlowScannerService:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def scan(self, config, limit=200, log_callback=None, snapshot_callback=None, cancel_check=None):
        self.started.set()
        while True:
            if cancel_check and cancel_check():
                raise asyncio.CancelledError()
            await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_runner_cancel_active_scan_emits_cancelled_log_and_completed_payload():
    scanner = SlowScannerService()
    runner = QuantScanRunner(
        config_service=StubConfigService(),
        scanner_service=scanner,
    )

    log_messages: list[str] = []
    completed_payloads: list[dict] = []

    async def log_callback(message: str, log_type: str):
        log_messages.append(message)

    async def completed_callback(payload: dict):
        completed_payloads.append(payload)

    task = asyncio.create_task(
        runner.run_scan(
            log_callback=log_callback,
            completed_callback=completed_callback,
        )
    )
    await scanner.started.wait()

    assert runner.is_running() is True
    assert runner.cancel_active_scan() is True

    with pytest.raises(QuantScanCancelledError):
        await task

    assert runner.is_running() is False
    assert "Quant scan cancelled." in log_messages
    assert completed_payloads[-1]["cancelled"] is True


@pytest.mark.asyncio
async def test_runner_rejects_parallel_runs():
    scanner = SlowScannerService()
    runner = QuantScanRunner(
        config_service=StubConfigService(),
        scanner_service=scanner,
    )

    first = asyncio.create_task(runner.run_scan())
    await scanner.started.wait()

    with pytest.raises(QuantScanAlreadyRunningError):
        await runner.run_scan()

    runner.cancel_active_scan()
    with pytest.raises(QuantScanCancelledError):
        await first
