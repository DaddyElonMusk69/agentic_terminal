from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
from typing import List, Optional

from app.application.automation.prompt_request_builder import build_prompt_request
from app.application.automation.execution_mode import (
    ExecutionMode,
    normalize_execution_mode,
    should_execute_trades,
)
from app.application.automation import topics
from app.application.automation.history_service import AutomationHistoryService
from app.application.bus.outbox_service import OutboxService
from app.application.ema_scanner.config_service import EmaScannerConfigService
from app.application.ema_scanner.presenter import build_scan_results
from app.application.ema_scanner.service import EmaScannerService
from app.application.ema_state_manager.service import EmaStateManagerService
from app.application.ema_state_manager.presenter import build_vegas_state_payload
from app.application.pending_entry.service import PendingEntryService
from app.application.prompt_builder.queue_service import PromptBuildQueueService
from app.application.quant_scanner.config_service import QuantScannerConfigService
from app.application.quant_scanner.service import QuantScannerService
from app.application.quant_scanner.presenter import snapshot_to_signal
from app.application.portfolio.service import PortfolioService
from app.application.telegram.notifications_service import TelegramNotificationService
from app.domain.ema_scanner.models import EmaScannerSignal
from app.domain.ema_state_manager.models import PositionSnapshot
from app.domain.ema_state_manager.models import PendingEntrySnapshot


class AutomationPipelineService:
    def __init__(
        self,
        ema_scanner: EmaScannerService,
        ema_config: EmaScannerConfigService,
        ema_state_manager: EmaStateManagerService,
        quant_scanner: QuantScannerService,
        quant_config: QuantScannerConfigService,
        prompt_queue: PromptBuildQueueService,
        outbox: OutboxService,
        portfolio_service: PortfolioService,
        pending_entry_service: PendingEntryService | None = None,
        telegram_notifier: TelegramNotificationService | None = None,
        history_service: AutomationHistoryService | None = None,
    ) -> None:
        self._ema_scanner = ema_scanner
        self._ema_config = ema_config
        self._ema_state_manager = ema_state_manager
        self._quant_scanner = quant_scanner
        self._quant_config = quant_config
        self._prompt_queue = prompt_queue
        self._outbox = outbox
        self._portfolio_service = portfolio_service
        self._pending_entry_service = pending_entry_service
        self._telegram_notifier = telegram_notifier
        self._history_service = history_service

    async def run_ema_cycle(
        self,
        execution_mode: str | None = None,
        template_map: dict[str, int] | None = None,
        llm_model: str | None = None,
        llm_provider: str | None = None,
        llm_reasoning_effort: str | None = None,
        max_positions: int | None = None,
        include_entry_timing_15m_chart: bool = False,
        use_all_monitored_interval_charts: bool = False,
        session_id: str | None = None,
        cycle_number: int | None = None,
    ) -> dict:
        mode = normalize_execution_mode(execution_mode)
        positions = await self._fetch_positions(session_id=session_id, cycle_number=cycle_number)

        async def log_event(event: str, data: Optional[dict] = None) -> None:
            payload = {"event": event, "data": data or {}, "cycle_number": cycle_number}
            await self._outbox.enqueue_event(
                "scanner.ema.log",
                self._with_session(payload, session_id),
            )

        await log_event("scan_init")
        try:
            config = await self._ema_config.build_config(log_callback=log_event)
        except Exception as exc:
            await log_event("scan_error", {"error": str(exc)})
            raise

        await log_event(
            "scan_config",
            {
                "assets_count": len(config.assets),
                "timeframes_count": len(config.timeframes),
                "ema_lines_count": len(config.ema_lengths),
                "tolerance_pct": config.tolerance_pct,
            },
        )

        await log_event(
            "scan_assets",
            {"assets": [asset.strip().upper() for asset in config.assets if asset.strip()]},
        )

        if not config.assets or not config.timeframes or not config.ema_lengths:
            await log_event(
                "scan_empty_config",
                {
                    "assets": len(config.assets),
                    "timeframes": len(config.timeframes),
                    "ema_lengths": len(config.ema_lengths),
                },
            )
            return {"signals": 0, "events": 0, "queued": 0}

        pending_entries = await self._fetch_pending_entries(quote_asset=config.quote_asset)
        chart_store: dict[str, dict[str, dict]] = {}
        state_config = await self._ema_state_manager.get_config()
        events = []
        queued = 0

        async def process_scanned_asset(
            symbol: str,
            asset_signals: List[EmaScannerSignal],
            _asset_charts: dict[str, dict],
        ) -> None:
            nonlocal queued

            asset_events = await self._ema_state_manager.process_signals(
                signals=asset_signals,
                monitored_assets=config.assets,
                quote_asset=config.quote_asset,
                open_positions=positions,
                max_open_positions=max_positions,
                pending_entries=pending_entries,
                update_assets=[symbol],
                prune_missing=False,
                state_config=state_config,
            )
            if not asset_events:
                return

            events.extend(asset_events)

            if self._telegram_notifier:
                for event in asset_events:
                    asyncio.create_task(
                        self._telegram_notifier.notify_ema_event(event, asset_signals)
                    )

            for event in asset_events:
                template_id = _resolve_template_id(event.trigger_reason.value, template_map)
                payload = build_prompt_request(
                    event,
                    config.timeframes,
                    template_id=template_id,
                    execution_mode=mode,
                    llm_model=llm_model,
                    llm_provider=llm_provider,
                    llm_reasoning_effort=llm_reasoning_effort,
                    include_entry_timing_15m_chart=include_entry_timing_15m_chart,
                    use_all_monitored_interval_charts=use_all_monitored_interval_charts,
                    session_id=session_id,
                )
                payload["cycle_number"] = cycle_number
                await self._prompt_queue.enqueue(payload)
                await self._outbox.enqueue_event(
                    topics.PROMPT_REQUESTED,
                    self._with_session(payload, session_id),
                )
                queued += 1

        signals = await self._ema_scanner.scan(
            config,
            log_callback=log_event,
            chart_store=chart_store,
            asset_callback=process_scanned_asset,
        )

        await log_event(
            "scan_finished",
            {"signals": len(signals)},
        )

        await self._outbox.enqueue_event(
            topics.EMA_SIGNALS,
            self._with_session(
                {
                    "count": len(signals),
                    "signals": [asdict(signal) for signal in signals],
                    "cycle_number": cycle_number,
                },
                session_id,
            ),
        )

        await self._ema_state_manager.process_signals(
            signals=[],
            monitored_assets=config.assets,
            quote_asset=config.quote_asset,
            open_positions=positions,
            max_open_positions=max_positions,
            pending_entries=pending_entries,
            update_assets=[],
            prune_missing=True,
            state_config=state_config,
        )
        await log_event(
            "state_processed",
            {
                "signals": len(signals),
                "events": len(events),
                "tickers": list({event.symbol for event in events}),
            },
        )
        state_payload = build_vegas_state_payload(
            self._ema_state_manager.get_all_states(),
            state_config,
        )
        if cycle_number is not None:
            state_payload["cycle_number"] = cycle_number
        await self._outbox.enqueue_event(
            topics.EMA_STATE,
            self._with_session(state_payload, session_id),
        )

        results = build_scan_results(signals, config.timeframes, chart_store)
        await self._outbox.enqueue_event(
            topics.EMA_RESULTS,
            self._with_session({"results": results, "cycle_number": cycle_number}, session_id),
        )

        synced_external_trades = 0
        if should_execute_trades(mode):
            synced_external_trades = await self._sync_external_trades(
                session_id=session_id,
                cycle_number=cycle_number,
            )
            if synced_external_trades > 0:
                await log_event("exchange_trades_synced", {"count": synced_external_trades})

        return {
            "signals": len(signals),
            "events": len(events),
            "queued": queued,
            "synced_external_trades": synced_external_trades,
        }

    async def run_quant_cycle(self, limit: int = 200, session_id: str | None = None) -> dict:
        config = await self._quant_config.build_config()

        async def log_event(message: str, log_type: str) -> None:
            payload = {
                "message": message,
                "type": log_type,
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
            await self._outbox.enqueue_event(
                "scanner.quant.log",
                self._with_session(payload, session_id),
            )

        async def emit_signal(snapshot) -> None:
            payload = snapshot_to_signal(snapshot)
            await self._outbox.enqueue_event(
                "scanner.quant.signal",
                self._with_session(payload, session_id),
            )

        await log_event(
            f"Quant config · {len(config.assets)} assets × {len(config.timeframes)} intervals",
            "info",
        )
        await log_event("━━━ SCAN CYCLE #1 STARTED ━━━", "cycle-start")
        snapshots = await self._quant_scanner.scan(
            config,
            limit=limit,
            log_callback=log_event,
            snapshot_callback=emit_signal,
        )

        await self._outbox.enqueue_event(
            topics.QUANT_SCAN_COMPLETED,
            self._with_session(
                {
                    "count": len(snapshots),
                    "assets": config.assets,
                    "timeframes": config.timeframes,
                },
                session_id,
            ),
        )
        await log_event("━━━ CYCLE #1 COMPLETE ━━━", "cycle-end")
        await log_event(f"Results: {len(snapshots)} snapshots", "info")

        return {"snapshots": len(snapshots)}

    async def _fetch_positions(
        self,
        session_id: str | None = None,
        cycle_number: int | None = None,
    ) -> List[PositionSnapshot]:
        try:
            snapshot = await self._portfolio_service.get_portfolio_snapshot()
        except Exception as exc:
            payload = {
                "message": "Portfolio snapshot unavailable; skipping positions.",
                "error": str(exc),
                "error_type": type(exc).__name__,
                "cycle_number": cycle_number,
            }
            await self._outbox.enqueue_event(
                topics.PIPELINE_POSITIONS_UNAVAILABLE,
                self._with_session(payload, session_id),
            )
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

    async def _fetch_pending_entries(self, quote_asset: str = "USDT") -> List[PendingEntrySnapshot]:
        if self._pending_entry_service is None:
            return []
        try:
            entries = await self._pending_entry_service.list_active_snapshots_for_active_account()
        except Exception:
            return []
        return [
            PendingEntrySnapshot(
                symbol=_normalize_market_symbol(entry.symbol, quote_asset),
                side=entry.side,
                limit_price=entry.limit_price,
                placed_at=entry.placed_at,
                expires_at=entry.expires_at,
                order_id=entry.exchange_order_id,
            )
            for entry in entries
        ]

    async def _sync_external_trades(
        self,
        session_id: str | None,
        cycle_number: int | None,
    ) -> int:
        if not session_id or self._history_service is None:
            return 0
        try:
            recent_trades = await self._portfolio_service.get_recent_trades(limit=50)
        except Exception:
            return 0
        if not isinstance(recent_trades, list) or not recent_trades:
            return 0
        try:
            return await self._history_service.sync_external_trades(
                session_id=session_id,
                trades=recent_trades,
                cycle_number=cycle_number or 0,
            )
        except Exception:
            return 0

    def _with_session(self, payload: dict, session_id: Optional[str]) -> dict:
        if session_id:
            payload = dict(payload)
            payload["session_id"] = session_id
        return payload


def _resolve_template_id(trigger_reason: str, template_map: dict[str, int] | None) -> Optional[int]:
    if not template_map:
        return None
    value = template_map.get(trigger_reason)
    if value is None and trigger_reason == "resonance_refresh":
        value = template_map.get("new_resonance")
    if isinstance(value, int) and value > 0:
        return value
    return None


def _normalize_market_symbol(symbol: str, quote_asset: str) -> str:
    value = str(symbol or "").strip().upper()
    quote = str(quote_asset or "USDT").strip().upper() or "USDT"
    if not value:
        return ""
    if "/" in value or ":" in value:
        return value
    return f"{value}/{quote}"
