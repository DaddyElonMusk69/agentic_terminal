import inspect
from typing import Awaitable, Callable, List, Optional

from app.domain.ema_scanner.models import EmaScannerConfig, EmaScannerLine
from app.domain.ema_scanner.interfaces import EmaScannerConfigRepository
from app.application.monitored_assets.service import MonitoredAssetsService


LogCallback = Callable[[str, Optional[dict]], Awaitable[None] | None]


async def _emit_log(
    log_callback: Optional[LogCallback],
    event: str,
    data: Optional[dict] = None,
) -> None:
    if not log_callback:
        return
    result = log_callback(event, data)
    if inspect.isawaitable(result):
        await result


class EmaScannerConfigService:
    def __init__(
        self,
        repository: EmaScannerConfigRepository,
        assets_service: MonitoredAssetsService,
    ) -> None:
        self._repository = repository
        self._assets_service = assets_service

    async def build_config(
        self,
        quote_asset: str = "USDT",
        log_callback: Optional[LogCallback] = None,
    ) -> EmaScannerConfig:
        assets = await self._assets_service.list_assets()
        intervals = await self.get_effective_scan_intervals()
        ema_lines = await self._repository.list_ema_lines()
        tolerance = await self._repository.get_tolerance()

        if tolerance is None:
            await _emit_log(
                log_callback,
                "missing_tolerance",
                {"default": 0.2},
            )

        return EmaScannerConfig(
            assets=assets,
            timeframes=intervals,
            ema_lengths=ema_lines,
            tolerance_pct=tolerance or 0.2,
            quote_asset=quote_asset,
        )

    async def list_available_intervals(self) -> List[str]:
        return await self._repository.list_monitored_intervals()

    async def get_effective_scan_intervals(self) -> List[str]:
        monitored = await self._repository.list_monitored_intervals()
        configured = await self._repository.get_scan_intervals()
        return _resolve_effective_scan_intervals(monitored, configured)

    async def update_scan_intervals(self, intervals: List[str] | None) -> List[str]:
        monitored = await self._repository.list_monitored_intervals()
        stored = _normalize_scan_interval_selection(monitored, intervals)
        await self._repository.set_scan_intervals(stored)
        return _resolve_effective_scan_intervals(monitored, stored)

    async def list_lines(self) -> List[EmaScannerLine]:
        return await self._repository.list_ema_line_records()

    async def add_line(self, length: int) -> List[EmaScannerLine]:
        return await self._repository.add_ema_line(length)

    async def remove_line(self, line_id: int) -> List[EmaScannerLine]:
        return await self._repository.remove_ema_line(line_id)

    async def get_tolerance_value(self) -> float:
        return await self._repository.get_tolerance() or 0.2

    async def set_tolerance(self, value: float) -> float:
        return await self._repository.set_tolerance(value)


def _resolve_effective_scan_intervals(
    monitored: List[str],
    configured: List[str] | None,
) -> List[str]:
    normalized_monitored = _dedupe_strings(monitored)
    normalized_configured = _dedupe_strings(configured or [])
    if not normalized_configured:
        return normalized_monitored
    selected = [interval for interval in normalized_monitored if interval in normalized_configured]
    return selected or normalized_monitored


def _normalize_scan_interval_selection(
    monitored: List[str],
    requested: List[str] | None,
) -> List[str] | None:
    normalized_monitored = _dedupe_strings(monitored)
    normalized_requested = _dedupe_strings(requested or [])
    selected = [interval for interval in normalized_monitored if interval in normalized_requested]
    if not selected or selected == normalized_monitored:
        return None
    return selected


def _dedupe_strings(values: List[str]) -> List[str]:
    seen: set[str] = set()
    deduped: List[str] = []
    for item in values:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
