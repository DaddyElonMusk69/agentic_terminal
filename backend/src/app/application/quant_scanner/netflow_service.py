from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Dict, Optional, Any, Iterable

from app.domain.quant_scanner.models import NetflowMetrics
from app.infrastructure.external.nofxos_client import NofXOSClient


ApiKeyProvider = Callable[[], Awaitable[Optional[str]]]


class NetflowService:
    def __init__(
        self,
        client: Optional[NofXOSClient] = None,
        api_key_provider: Optional[ApiKeyProvider] = None,
    ) -> None:
        self._client = client or NofXOSClient()
        self._api_key_provider = api_key_provider
        self._api_key_checked = False

    def is_configured(self) -> bool:
        return self._client.is_configured()

    async def fetch_raw(self, symbol: str) -> Optional[Dict[str, Any]]:
        await self._ensure_api_key()
        if not self.is_configured():
            return None
        return await asyncio.to_thread(self._client.get_coin_data, symbol)

    async def _ensure_api_key(self) -> None:
        if self._client.is_configured():
            return
        if self._api_key_checked:
            return
        self._api_key_checked = True
        if not self._api_key_provider:
            return
        key = await self._api_key_provider()
        if key:
            self._client.set_api_key(key)

    def build_metrics(
        self, raw_data: Optional[Dict[str, Any]], timeframe: str
    ) -> Optional[NetflowMetrics]:
        if not raw_data:
            return None
        resolved = _resolve_timeframe(raw_data, timeframe)
        if not resolved:
            return None
        return NetflowMetrics.from_api_response(raw_data, resolved)


def _resolve_timeframe(raw_data: Dict[str, Any], timeframe: str) -> Optional[str]:
    inner = raw_data.get("data", raw_data)
    netflow = inner.get("netflow", {})
    institution = netflow.get("institution", {}).get("future", {})
    if not isinstance(institution, dict):
        return timeframe
    available = [key for key in institution.keys() if isinstance(key, str)]
    if timeframe in available:
        return timeframe
    return _closest_timeframe(timeframe, available)


def _closest_timeframe(target: str, candidates: Iterable[str]) -> Optional[str]:
    target_minutes = _timeframe_to_minutes(target)
    if target_minutes is None:
        return None
    best: Optional[str] = None
    best_delta: Optional[int] = None
    for candidate in candidates:
        candidate_minutes = _timeframe_to_minutes(candidate)
        if candidate_minutes is None:
            continue
        delta = abs(candidate_minutes - target_minutes)
        if best_delta is None or delta < best_delta:
            best_delta = delta
            best = candidate
    return best


def _timeframe_to_minutes(timeframe: str) -> Optional[int]:
    value = timeframe.strip().lower()
    if value.endswith("m") and value[:-1].isdigit():
        return int(value[:-1])
    if value.endswith("h") and value[:-1].isdigit():
        return int(value[:-1]) * 60
    if value.endswith("d") and value[:-1].isdigit():
        return int(value[:-1]) * 1440
    return None
