from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from app.application.automation.pipeline import AutomationPipelineService

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AutomationScheduler:
    def __init__(
        self,
        pipeline: AutomationPipelineService,
        ema_interval_seconds: int,
        quant_interval_seconds: int,
        execution_mode: str = "dry_run",
        template_map: Optional[dict[str, int]] = None,
        llm_model: Optional[str] = None,
        llm_provider: Optional[str] = None,
        include_entry_timing_15m_chart: bool = False,
        use_all_monitored_interval_charts: bool = False,
        session_id: Optional[str] = None,
    ) -> None:
        self._pipeline = pipeline
        self._ema_interval = max(1, int(ema_interval_seconds))
        self._quant_interval = max(1, int(quant_interval_seconds))
        self._execution_mode = execution_mode
        self._template_map = dict(template_map or {})
        self._llm_model = llm_model
        self._llm_provider = llm_provider
        self._include_entry_timing_15m_chart = bool(include_entry_timing_15m_chart)
        self._use_all_monitored_interval_charts = bool(use_all_monitored_interval_charts)
        self._session_id = session_id
        self._stop_event = asyncio.Event()
        self._tasks: list[asyncio.Task] = []
        self._ema_cycles = 0
        self._quant_cycles = 0
        self._last_ema_cycle_at: Optional[datetime] = None
        self._last_quant_cycle_at: Optional[datetime] = None

    async def start(self) -> None:
        self._stop_event.clear()
        self._tasks = [
            asyncio.create_task(self._run_ema_loop()),
            asyncio.create_task(self._run_quant_loop()),
        ]

    async def stop(self) -> None:
        self._stop_event.set()
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    async def _run_ema_loop(self) -> None:
        while not self._stop_event.is_set():
            cycle_number = self._ema_cycles + 1
            try:
                await self._pipeline.run_ema_cycle(
                    execution_mode=self._execution_mode,
                    template_map=self._template_map,
                    llm_model=self._llm_model,
                    llm_provider=self._llm_provider,
                    include_entry_timing_15m_chart=self._include_entry_timing_15m_chart,
                    use_all_monitored_interval_charts=self._use_all_monitored_interval_charts,
                    session_id=self._session_id,
                    cycle_number=cycle_number,
                )
            except Exception as exc:
                logger.exception("EMA cycle failed: %s", exc)
            finally:
                self._ema_cycles += 1
                self._last_ema_cycle_at = _utcnow()
            await self._sleep(self._ema_interval)

    async def _run_quant_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self._pipeline.run_quant_cycle(session_id=self._session_id)
            except Exception as exc:
                logger.exception("Quant cycle failed: %s", exc)
            finally:
                self._quant_cycles += 1
                self._last_quant_cycle_at = _utcnow()
            await self._sleep(self._quant_interval)

    async def _sleep(self, seconds: int) -> None:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            return

    def stats(self) -> dict:
        return {
            "ema_cycles": self._ema_cycles,
            "quant_cycles": self._quant_cycles,
            "last_ema_cycle_at": self._last_ema_cycle_at,
            "last_quant_cycle_at": self._last_quant_cycle_at,
        }

    @property
    def session_id(self) -> Optional[str]:
        return self._session_id
