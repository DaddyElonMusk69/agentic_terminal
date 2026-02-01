from __future__ import annotations

import inspect
from typing import Awaitable, Callable, Dict, List, Optional

from app.application.ema_scanner.config_service import EmaScannerConfigService
from app.application.ema_scanner.presenter import build_scan_results
from app.application.ema_scanner.service import EmaScannerService
from app.application.ema_state_manager.presenter import build_vegas_state_payload
from app.application.ema_state_manager.service import EmaStateManagerService
from app.application.portfolio.service import PortfolioService
from app.application.scanner_results.service import ScannerResultsService
from app.domain.ema_state_manager.models import PositionSnapshot


LogCallback = Callable[[str, Optional[dict]], Awaitable[None] | None]
StateCallback = Callable[[dict], Awaitable[None] | None]


class EmaConfigLoadError(RuntimeError):
    pass


class EmaScanRunError(RuntimeError):
    pass


async def _emit_log(
    log_callback: Optional[LogCallback],
    event: str,
    data: Optional[dict] = None,
    cycle_number: Optional[int] = None,
) -> None:
    if not log_callback:
        return
    payload = dict(data or {})
    if cycle_number is not None:
        payload.setdefault("cycle_number", cycle_number)
    result = log_callback(event, payload)
    if inspect.isawaitable(result):
        await result


async def _emit_state(
    state_callback: Optional[StateCallback],
    payload: dict,
    cycle_number: Optional[int] = None,
) -> None:
    if not state_callback:
        return
    data = dict(payload)
    if cycle_number is not None:
        data["cycle_number"] = cycle_number
    result = state_callback(data)
    if inspect.isawaitable(result):
        await result


class EmaScanRunner:
    def __init__(
        self,
        config_service: EmaScannerConfigService,
        scanner_service: EmaScannerService,
        results_service: ScannerResultsService,
        state_service: EmaStateManagerService,
        portfolio_service: PortfolioService,
    ) -> None:
        self._config_service = config_service
        self._scanner_service = scanner_service
        self._results_service = results_service
        self._state_service = state_service
        self._portfolio_service = portfolio_service
        self._cycle_number = 0

    async def run_scan(
        self,
        log_callback: Optional[LogCallback] = None,
        state_callback: Optional[StateCallback] = None,
    ) -> List[dict]:
        self._cycle_number += 1
        cycle_number = self._cycle_number

        await _emit_log(log_callback, "scan_init", cycle_number=cycle_number)

        try:
            async def wrapped_log(event: str, data: Optional[dict] = None) -> None:
                await _emit_log(log_callback, event, data, cycle_number)

            config = await self._config_service.build_config(log_callback=wrapped_log)
        except Exception as exc:
            await _emit_log(
                log_callback,
                "scan_error",
                {"error": str(exc)},
                cycle_number=cycle_number,
            )
            raise EmaConfigLoadError(str(exc)) from exc

        await _emit_log(
            log_callback,
            "scan_config",
            {
                "assets_count": len(config.assets),
                "timeframes_count": len(config.timeframes),
                "ema_lines_count": len(config.ema_lengths),
                "tolerance_pct": config.tolerance_pct,
            },
            cycle_number=cycle_number,
        )

        await _emit_log(
            log_callback,
            "scan_assets",
            {"assets": [asset.strip().upper() for asset in config.assets if asset.strip()]},
            cycle_number=cycle_number,
        )

        if not config.assets or not config.timeframes or not config.ema_lengths:
            await _emit_log(
                log_callback,
                "scan_empty_config",
                {
                    "assets": len(config.assets),
                    "timeframes": len(config.timeframes),
                    "ema_lengths": len(config.ema_lengths),
                },
                cycle_number=cycle_number,
            )
            return []

        chart_store: Dict[str, Dict[str, dict]] = {}
        try:
            signals = await self._scanner_service.scan(
                config,
                log_callback=wrapped_log,
                chart_store=chart_store,
            )
        except KeyError as exc:
            await _emit_log(
                log_callback,
                "scan_error",
                {"error": str(exc)},
                cycle_number=cycle_number,
            )
            raise
        except Exception as exc:
            await _emit_log(
                log_callback,
                "scan_error",
                {"error": str(exc)},
                cycle_number=cycle_number,
            )
            raise EmaScanRunError(str(exc)) from exc

        await _emit_log(
            log_callback,
            "scan_finished",
            {"signals": len(signals)},
            cycle_number=cycle_number,
        )

        results = build_scan_results(signals, config.timeframes, chart_store)

        positions = await self._fetch_positions()
        events = await self._state_service.process_signals(
            signals=signals,
            monitored_assets=config.assets,
            quote_asset=config.quote_asset,
            open_positions=positions,
        )
        await _emit_log(
            log_callback,
            "state_processed",
            {
                "signals": len(signals),
                "events": len(events),
                "tickers": list({event.symbol for event in events}),
            },
            cycle_number=cycle_number,
        )
        state_config = await self._state_service.get_config()
        state_payload = build_vegas_state_payload(self._state_service.get_all_states(), state_config)
        await _emit_state(state_callback, state_payload, cycle_number=cycle_number)

        response_payload: List[dict] = []
        if results:
            try:
                response_payload = await self._results_service.save_scan_results(results)
            except Exception as exc:
                await _emit_log(
                    log_callback,
                    "scan_error",
                    {"error": f"Failed to save scan results: {exc}"},
                )
                response_payload = results
        return response_payload

    async def _fetch_positions(self) -> List[PositionSnapshot]:
        try:
            snapshot = await self._portfolio_service.get_portfolio_snapshot()
        except Exception:
            return []

        positions: List[PositionSnapshot] = []
        for position in snapshot.positions:
            positions.append(
                PositionSnapshot(
                    symbol=position.symbol,
                    direction=position.direction,
                    entry_price=position.entry_price,
                )
            )
        return positions
