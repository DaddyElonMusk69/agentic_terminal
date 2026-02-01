from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Optional
from uuid import uuid4

from app.application.automation.dependencies import (
    get_prompt_pipeline_worker,
    get_llm_queue_worker,
    get_order_queue_worker,
    get_automation_pipeline_service,
    get_outbox_service,
)
from app.application.automation.execution_mode import normalize_execution_mode
from app.application.automation.scheduler import AutomationScheduler
from app.infrastructure.bus.dispatcher import OutboxDispatcher
from app.infrastructure.bus.outbox_repository import OutboxRepository
from app.infrastructure.bus.socketio_publisher import SocketIOPublisher
from app.infrastructure.db import get_sessionmaker
from app.realtime.hub import hub

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _format_dt(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.isoformat()


@dataclass(frozen=True)
class AutomationRuntimeConfig:
    execution_mode: str = "dry_run"
    ema_interval_seconds: int = 60
    quant_interval_seconds: int = 60
    provider: Optional[str] = None
    model: Optional[str] = None
    vegas_prompt_configs: Optional[dict[str, int]] = None
    session_id: Optional[str] = None


class AutomationRuntime:
    OUTBOX_PURGE_HOURS = 6
    OUTBOX_PURGE_INTERVAL_SECONDS = 300

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._stop_event = asyncio.Event()
        self._scheduler: Optional[AutomationScheduler] = None
        self._tasks: list[asyncio.Task] = []
        self._config = AutomationRuntimeConfig()
        self._running = False
        self._started_at: Optional[datetime] = None
        self._session_id: Optional[str] = None
        self._last_outbox_purge_at: Optional[datetime] = None

    async def start(self, config: AutomationRuntimeConfig) -> dict:
        async with self._lock:
            await self._stop_locked()
            normalized = _normalize_config(config)
            self._config = normalized
            self._stop_event.clear()

            session_id = normalized.session_id or str(uuid4())
            self._scheduler = AutomationScheduler(
                pipeline=get_automation_pipeline_service(),
                ema_interval_seconds=normalized.ema_interval_seconds,
                quant_interval_seconds=normalized.quant_interval_seconds,
                execution_mode=normalized.execution_mode,
                template_map=normalized.vegas_prompt_configs,
                llm_model=normalized.model,
                llm_provider=normalized.provider,
                session_id=session_id,
            )
            await self._scheduler.start()

            self._tasks = [
                asyncio.create_task(self._run_prompt_loop()),
                asyncio.create_task(self._run_llm_loop()),
                asyncio.create_task(self._run_order_loop()),
                asyncio.create_task(self._run_outbox_loop()),
            ]
            self._running = True
            self._started_at = _utcnow()
            self._session_id = self._scheduler.session_id
            self._last_outbox_purge_at = None
            return self.snapshot()

    async def stop(self) -> dict:
        async with self._lock:
            await self._stop_locked()
            return self.snapshot()

    def snapshot(self) -> dict:
        stats = self._scheduler.stats() if self._scheduler else {}
        ema_cycles = stats.get("ema_cycles", 0)
        quant_cycles = stats.get("quant_cycles", 0)

        return {
            "is_running": self._running,
            "session_id": self._session_id,
            "execution_mode": self._config.execution_mode,
            "ema_interval_seconds": self._config.ema_interval_seconds,
            "quant_interval_seconds": self._config.quant_interval_seconds,
            "provider": self._config.provider,
            "model": self._config.model,
            "vegas_prompt_configs": self._config.vegas_prompt_configs,
            "started_at": _format_dt(self._started_at),
            "current_cycle": ema_cycles,
            "ema_cycles": ema_cycles,
            "quant_cycles": quant_cycles,
            "last_ema_cycle_at": _format_dt(stats.get("last_ema_cycle_at")),
            "last_quant_cycle_at": _format_dt(stats.get("last_quant_cycle_at")),
        }

    async def _stop_locked(self) -> None:
        self._stop_event.set()
        if self._scheduler is not None:
            await self._scheduler.stop()
            self._scheduler = None
        if self._tasks:
            for task in self._tasks:
                task.cancel()
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks = []
        self._running = False
        self._started_at = None
        self._last_outbox_purge_at = None

    async def _run_prompt_loop(self) -> None:
        worker = get_prompt_pipeline_worker()
        await self._run_queue_loop("prompt", worker.process_next, idle_delay=1.0)

    async def _run_llm_loop(self) -> None:
        worker = get_llm_queue_worker()
        await self._run_queue_loop("llm", worker.process_next, idle_delay=1.0)

    async def _run_order_loop(self) -> None:
        worker = get_order_queue_worker()
        await self._run_queue_loop("order", worker.process_next, idle_delay=1.0)

    async def _run_outbox_loop(self) -> None:
        repository = OutboxRepository(get_sessionmaker())
        dispatcher = OutboxDispatcher(repository, SocketIOPublisher(hub))
        outbox = get_outbox_service()

        while not self._stop_event.is_set():
            try:
                dispatched = await dispatcher.dispatch(limit=100)
                await self._maybe_purge_outbox(repository, outbox)
                if dispatched == 0:
                    await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Outbox dispatch loop failed: %s", exc)
                await asyncio.sleep(1.0)

    async def _run_queue_loop(
        self,
        name: str,
        handler,
        idle_delay: float,
    ) -> None:
        while not self._stop_event.is_set():
            try:
                handled = await handler()
                if not handled:
                    await asyncio.sleep(idle_delay)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("%s queue loop failed: %s", name, exc)
                await asyncio.sleep(idle_delay)

    async def _maybe_purge_outbox(self, repository: OutboxRepository, outbox: OutboxService) -> None:
        now = _utcnow()
        if self._last_outbox_purge_at is not None:
            elapsed = (now - self._last_outbox_purge_at).total_seconds()
            if elapsed < self.OUTBOX_PURGE_INTERVAL_SECONDS:
                return
        cutoff = now - timedelta(hours=self.OUTBOX_PURGE_HOURS)
        purged = await repository.delete_older_than(
            cutoff,
            statuses=("processed", "failed"),
        )
        self._last_outbox_purge_at = now
        if purged <= 0:
            return
        payload = {
            "event": "outbox_purge",
            "data": {
                "purged": purged,
                "cutoff_hours": self.OUTBOX_PURGE_HOURS,
            },
        }
        if self._session_id:
            payload["session_id"] = self._session_id
        await outbox.enqueue_event("scanner.ema.log", payload)


def _normalize_config(config: AutomationRuntimeConfig) -> AutomationRuntimeConfig:
    mode = normalize_execution_mode(config.execution_mode).value
    provider = config.provider.strip() if config.provider else None
    model = config.model.strip() if config.model else None
    prompt_map = _normalize_prompt_map(config.vegas_prompt_configs)

    return AutomationRuntimeConfig(
        execution_mode=mode,
        ema_interval_seconds=max(1, int(config.ema_interval_seconds)),
        quant_interval_seconds=max(1, int(config.quant_interval_seconds)),
        provider=provider or None,
        model=model or None,
        vegas_prompt_configs=prompt_map,
        session_id=config.session_id or None,
    )


def _normalize_prompt_map(values: Optional[dict[str, int]]) -> Optional[dict[str, int]]:
    if not values:
        return None
    cleaned: dict[str, int] = {}
    for key, value in values.items():
        if not key:
            continue
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            cleaned[str(key)] = parsed
    return cleaned or None


@lru_cache(maxsize=1)
def get_automation_runtime() -> AutomationRuntime:
    return AutomationRuntime()
