from __future__ import annotations

import asyncio
import inspect
from typing import Awaitable, Callable, List, Optional

from app.application.quant_scanner.config_service import QuantScannerConfigService
from app.application.quant_scanner.presenter import snapshot_to_signal
from app.application.quant_scanner.service import QuantScannerService


LogCallback = Callable[[str, str], Awaitable[None] | None]
SignalCallback = Callable[[dict], Awaitable[None] | None]
CompletedCallback = Callable[[dict], Awaitable[None] | None]


class QuantConfigLoadError(RuntimeError):
    pass


class QuantScanRunError(RuntimeError):
    pass


class QuantScanAlreadyRunningError(RuntimeError):
    pass


class QuantScanCancelledError(RuntimeError):
    pass


async def _emit_log(
    log_callback: Optional[LogCallback],
    message: str,
    log_type: str,
) -> None:
    if not log_callback:
        return
    result = log_callback(message, log_type)
    if inspect.isawaitable(result):
        await result


async def _emit_signal(
    signal_callback: Optional[SignalCallback],
    payload: dict,
) -> None:
    if not signal_callback:
        return
    result = signal_callback(payload)
    if inspect.isawaitable(result):
        await result


async def _emit_completed(
    completed_callback: Optional[CompletedCallback],
    payload: dict,
) -> None:
    if not completed_callback:
        return
    result = completed_callback(payload)
    if inspect.isawaitable(result):
        await result


class QuantScanRunner:
    def __init__(
        self,
        config_service: QuantScannerConfigService,
        scanner_service: QuantScannerService,
    ) -> None:
        self._config_service = config_service
        self._scanner_service = scanner_service
        self._run_lock = asyncio.Lock()
        self._active_task: asyncio.Task | None = None
        self._cancel_requested = False

    async def run_scan(
        self,
        log_callback: Optional[LogCallback] = None,
        signal_callback: Optional[SignalCallback] = None,
        completed_callback: Optional[CompletedCallback] = None,
        limit: int = 200,
    ) -> List[dict]:
        if self._run_lock.locked():
            raise QuantScanAlreadyRunningError("Quant scan is already running")

        async with self._run_lock:
            self._cancel_requested = False
            self._active_task = asyncio.current_task()
            try:
                return await self._run_scan_inner(
                    log_callback=log_callback,
                    signal_callback=signal_callback,
                    completed_callback=completed_callback,
                    limit=limit,
                )
            except asyncio.CancelledError as exc:
                await _emit_completed(
                    completed_callback,
                    {"cancelled": True},
                )
                await _emit_log(log_callback, "Quant scan cancelled.", "warning")
                raise QuantScanCancelledError("Quant scan cancelled") from exc
            finally:
                self._active_task = None
                self._cancel_requested = False

    async def _run_scan_inner(
        self,
        log_callback: Optional[LogCallback] = None,
        signal_callback: Optional[SignalCallback] = None,
        completed_callback: Optional[CompletedCallback] = None,
        limit: int = 200,
    ) -> List[dict]:
        await _emit_log(log_callback, "━━━ SCAN CYCLE #1 STARTED ━━━", "cycle-start")

        try:
            config = await self._config_service.build_config()
        except Exception as exc:
            await _emit_log(log_callback, f"⚠ Failed to load quant scanner config: {exc}", "error")
            raise QuantConfigLoadError(str(exc)) from exc

        if not config.assets or not config.timeframes:
            await _emit_log(
                log_callback,
                "⚠ No assets or intervals configured for quant scan.",
                "warning",
            )
            return []

        await _emit_log(
            log_callback,
            f"🔄 Scanning {len(config.assets)} assets × {len(config.timeframes)} intervals",
            "info",
        )
        await _emit_log(
            log_callback,
            f"Assets: {', '.join(asset.strip().upper() for asset in config.assets if asset.strip())}",
            "info",
        )

        results: List[dict] = []

        async def emit_signal(snapshot) -> None:
            signal = snapshot_to_signal(snapshot)
            results.append(signal)
            await _emit_signal(signal_callback, signal)

        try:
            snapshots = await self._scanner_service.scan(
                config,
                limit=limit,
                log_callback=log_callback,
                snapshot_callback=emit_signal,
                cancel_check=self._is_cancel_requested,
            )
        except Exception as exc:
            await _emit_log(log_callback, f"⚠ Quant scan failed: {exc}", "error")
            raise QuantScanRunError(str(exc)) from exc

        if not results and snapshots:
            results = [snapshot_to_signal(snapshot) for snapshot in snapshots]

        await _emit_completed(
            completed_callback,
            {
                "count": len(results),
                "assets": config.assets,
                "timeframes": config.timeframes,
                "cancelled": False,
            },
        )

        await _emit_log(log_callback, "━━━ CYCLE #1 COMPLETE ━━━", "cycle-end")
        await _emit_log(log_callback, f"Results: {len(results)} snapshots", "info")

        return results

    def is_running(self) -> bool:
        return bool(self._active_task and not self._active_task.done())

    def cancel_active_scan(self) -> bool:
        task = self._active_task
        if task is None or task.done():
            return False
        self._cancel_requested = True
        return True

    def _is_cancel_requested(self) -> bool:
        return self._cancel_requested
