from __future__ import annotations

import asyncio
import logging
from functools import lru_cache

from app.application.protection_reconciler.dependencies import get_protection_reconciler_service
from app.application.protection_reconciler.service import ProtectionReconcilerService

logger = logging.getLogger(__name__)


class ProtectionReconcilerRuntime:
    def __init__(self, service: ProtectionReconcilerService | None = None) -> None:
        self._service = service or get_protection_reconciler_service()
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        async with self._lock:
            if self.is_running():
                return
            self._stop_event.clear()
            self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        async with self._lock:
            self._stop_event.set()
            if self._task is None:
                return
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self._service.poll_once()
                await asyncio.sleep(self._service.POLL_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("position protection background loop failed: %s", exc)
                await asyncio.sleep(self._service.POLL_INTERVAL_SECONDS)


@lru_cache(maxsize=1)
def get_protection_reconciler_runtime() -> ProtectionReconcilerRuntime:
    return ProtectionReconcilerRuntime()
