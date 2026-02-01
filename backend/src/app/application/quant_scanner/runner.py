from __future__ import annotations

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

    async def run_scan(
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
            )
        except Exception as exc:
            await _emit_log(log_callback, f"⚠ Quant scan failed: {exc}", "error")
            raise QuantScanRunError(str(exc)) from exc

        if not results and snapshots:
            results = [snapshot_to_signal(snapshot) for snapshot in snapshots]

        await _emit_completed(
            completed_callback,
            {"count": len(results), "assets": config.assets, "timeframes": config.timeframes},
        )

        await _emit_log(log_callback, "━━━ CYCLE #1 COMPLETE ━━━", "cycle-end")
        await _emit_log(log_callback, f"Results: {len(results)} snapshots", "info")

        return results
