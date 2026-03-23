from __future__ import annotations

"""Dynamic asset resolver that combines cached OI rank data with NOFX OS sources."""

from typing import Any, Dict, List, Optional

from app.application.oi_rank.service import OiRankService
from app.infrastructure.external.nofxos_dynamic_assets import NofXOSDynamicAssetsClient


class OiRankDynamicAssetsClient:
    def __init__(
        self,
        oi_rank_service: OiRankService,
        nofx_client: Optional[NofXOSDynamicAssetsClient] = None,
    ) -> None:
        self._oi_rank = oi_rank_service
        self._nofx = nofx_client or NofXOSDynamicAssetsClient()

    async def fetch_multi_source_assets(
        self,
        sources: Dict[str, Any],
        api_key: Optional[str],
    ) -> List[str]:
        assets: List[str] = []

        ai_sources = _strip_oi_sources(sources)
        if _has_ai_sources(ai_sources):
            assets.extend(await self._nofx.fetch_multi_source_assets(ai_sources, api_key))

        oi_top = sources.get("oi_top", {}) if isinstance(sources, dict) else {}
        if oi_top.get("enabled"):
            interval = str(oi_top.get("duration", "1h"))
            limit = int(oi_top.get("limit", 5))
            result = await self._oi_rank.get_rank(
                direction="top",
                interval=interval,
                limit=limit,
                metric="abs",
            )
            assets.extend(_extract_symbols(result))

        oi_low = sources.get("oi_low", {}) if isinstance(sources, dict) else {}
        if oi_low.get("enabled"):
            interval = str(oi_low.get("duration", "1h"))
            limit = int(oi_low.get("limit", 5))
            result = await self._oi_rank.get_rank(
                direction="low",
                interval=interval,
                limit=limit,
                metric="abs",
            )
            assets.extend(_extract_symbols(result))

        return _dedup_preserve_order(assets)


def _extract_symbols(result) -> List[str]:
    if not result.entries:
        return []
    symbols: List[str] = []
    for entry in result.entries:
        symbol = entry.symbol
        if isinstance(symbol, str) and symbol:
            symbols.append(symbol)
    return symbols


def _strip_oi_sources(sources: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(sources, dict):
        return {}
    stripped = {key: dict(value) for key, value in sources.items() if isinstance(value, dict)}
    if "oi_top" in stripped:
        stripped["oi_top"]["enabled"] = False
    if "oi_low" in stripped:
        stripped["oi_low"]["enabled"] = False
    return stripped


def _has_ai_sources(sources: Dict[str, Any]) -> bool:
    for key in ("ai500", "ai300"):
        if sources.get(key, {}).get("enabled"):
            return True
    return False


def _dedup_preserve_order(items: List[str]) -> List[str]:
    seen: set[str] = set()
    result: List[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
