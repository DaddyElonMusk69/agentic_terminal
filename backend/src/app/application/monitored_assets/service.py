from __future__ import annotations

import logging
from typing import Iterable, List, Sequence

from app.application.dynamic_assets.service import DynamicAssetsService
from app.application.market_settings.service import MarketSettingsService
from app.infrastructure.repositories.monitored_asset_position_repository import (
    MonitoredAssetPositionRepository,
)


logger = logging.getLogger(__name__)


class MonitoredAssetsService:
    """Single source of truth for monitored assets (dynamic list + manual + positions)."""

    def __init__(
        self,
        market_settings: MarketSettingsService,
        dynamic_assets: DynamicAssetsService,
        position_repository: MonitoredAssetPositionRepository,
    ) -> None:
        self._market_settings = market_settings
        self._dynamic_assets = dynamic_assets
        self._position_repository = position_repository

    async def list_assets(
        self,
        include_positions: bool = True,
        force_refresh: bool = False,
    ) -> List[str]:
        base_assets = await self._resolve_base_assets(force_refresh=force_refresh)
        if not include_positions:
            return base_assets
        extras = await self._position_repository.list_assets()
        return _merge_assets(base_assets, extras)

    async def append_positions(self, positions: Sequence[object]) -> None:
        symbols = _extract_position_symbols(positions)
        if not symbols:
            return
        await self._position_repository.add_assets(symbols)

    async def sync_positions(self, positions: Sequence[object]) -> None:
        symbols = _extract_position_symbols(positions)
        await self._position_repository.sync_assets(symbols)

    async def _resolve_base_assets(self, force_refresh: bool = False) -> List[str]:
        state = await self._dynamic_assets.resolve_assets(force_refresh=force_refresh)
        if state.enabled and state.binance_active:
            if state.assets:
                return _normalize_assets(state.assets)
            if state.is_stale:
                logger.warning("Dynamic assets stale; using empty list while enabled.")
            else:
                logger.warning("Dynamic assets unavailable; using empty list while enabled.")
            return []

        manual = await self._market_settings.list_assets()
        return _normalize_assets(manual)


def _merge_assets(base_assets: Iterable[str], extras: Iterable[str]) -> List[str]:
    seen = set()
    merged: List[str] = []

    for asset in base_assets:
        normalized = _normalize_asset(asset)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        merged.append(normalized)

    extra_list = sorted({_normalize_asset(asset) for asset in extras if _normalize_asset(asset)})
    for asset in extra_list:
        if asset in seen:
            continue
        seen.add(asset)
        merged.append(asset)

    return merged


def _normalize_assets(assets: Iterable[str]) -> List[str]:
    return _merge_assets(assets, [])


def _extract_position_symbols(positions: Sequence[object]) -> List[str]:
    symbols: List[str] = []
    for position in positions:
        symbol = None
        if isinstance(position, str):
            symbol = position
        elif hasattr(position, "symbol"):
            symbol = getattr(position, "symbol", None)
        elif isinstance(position, dict):
            symbol = position.get("symbol")
        if symbol:
            normalized = _normalize_asset(str(symbol))
            if normalized:
                symbols.append(normalized)
    return symbols


def _normalize_asset(symbol: str) -> str:
    value = symbol.strip().upper()
    if not value:
        return ""
    if "/" in value or ":" in value:
        value = value.replace(":", "/")
        value = value.split("/")[0]
    for suffix in ("-PERP", "PERP", "USDT", "-USD", "USD", "-USDC", "USDC"):
        if value.endswith(suffix):
            value = value[: -len(suffix)]
            break
    return value
