from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import asyncio
import logging
from typing import Any, Dict, Iterable, Optional

from app.common.errors import AppError
from app.domain.dynamic_assets.models import DynamicAssetsConfig, DynamicAssetsState
from app.domain.dynamic_assets.interfaces import DynamicAssetsConfigRepository
from app.infrastructure.external.binance_client import BinanceClient
from app.infrastructure.external.nofxos_dynamic_assets import NofXOSDynamicAssetsClient
from app.infrastructure.external.oi_rank_dynamic_assets import OiRankDynamicAssetsClient
from app.application.portfolio.service import PortfolioService


logger = logging.getLogger(__name__)

DEFAULT_REFRESH_INTERVAL_SECONDS = 600
MIN_REFRESH_INTERVAL_SECONDS = 60
MAX_REFRESH_INTERVAL_SECONDS = 3600
MAX_STALE_SECONDS = 1800
DEFAULT_24H_CHANGE_PCT = 20.0
MIN_24H_CHANGE_PCT = 5.0
MAX_24H_CHANGE_PCT = 100.0
DEFAULT_OI_SOURCE = "nofx"
SUPPORTED_OI_SOURCES = {"nofx", "custom"}

DEFAULT_SOURCES: Dict[str, Dict[str, Any]] = {
    "ai500": {"enabled": False, "limit": 10},
    "ai300": {"enabled": False, "limit": 20, "level": ""},
    "oi_top": {"enabled": False, "limit": 20, "duration": "1h"},
    "oi_low": {"enabled": False, "limit": 20, "duration": "1h"},
    "netflow_top": {"enabled": False, "limit": 20, "duration": "1h"},
    "netflow_low": {"enabled": False, "limit": 20, "duration": "1h"},
    "futures_depth": {"enabled": False, "limit": 60},
    "excluded_assets": {"enabled": False, "symbols": ""},
}


class DynamicAssetsService:
    def __init__(
        self,
        repository: DynamicAssetsConfigRepository,
        portfolio_service: PortfolioService,
        nofx_client: Optional[NofXOSDynamicAssetsClient] = None,
        oi_rank_client: Optional[OiRankDynamicAssetsClient] = None,
        default_oi_source: str = DEFAULT_OI_SOURCE,
        binance_client: Optional[BinanceClient] = None,
    ) -> None:
        self._repository = repository
        self._portfolio_service = portfolio_service
        self._nofx_client = nofx_client or NofXOSDynamicAssetsClient()
        self._oi_rank_client = oi_rank_client or self._nofx_client
        self._default_oi_source = _normalize_oi_source(default_oi_source, DEFAULT_OI_SOURCE)
        self._binance_client = binance_client or BinanceClient()
        self._last_removed_high_volatility: list[str] = []
        self._last_volatility_checked_at: Optional[datetime] = None

    async def get_config(self) -> DynamicAssetsConfig:
        config = await self._repository.get_config()
        if config is None:
            config = await self._repository.upsert(self._default_config())
        return self._normalize_config(config)

    async def update_config(
        self,
        enabled: bool,
        sources: Optional[Dict[str, Any]],
        refresh_interval_seconds: int,
        volatility_threshold_pct: Optional[float] = None,
        api_key: Optional[str] = None,
        update_api_key: bool = False,
        oi_source: Optional[str] = None,
    ) -> DynamicAssetsConfig:
        if refresh_interval_seconds < MIN_REFRESH_INTERVAL_SECONDS:
            raise AppError(
                code="dynamic_assets_refresh_interval_too_low",
                message="Refresh interval must be at least 60 seconds.",
            )
        if refresh_interval_seconds > MAX_REFRESH_INTERVAL_SECONDS:
            raise AppError(
                code="dynamic_assets_refresh_interval_too_high",
                message="Refresh interval must be 3600 seconds or less.",
            )

        if enabled and not await self._is_binance_active():
            raise AppError(
                code="dynamic_assets_requires_binance",
                message="Dynamic assets can only be enabled with an active Binance account.",
            )

        current = await self.get_config()
        source_payload = sources if sources is not None else current.sources
        normalized_sources = _normalize_sources(source_payload)
        next_api_key = current.api_key
        if update_api_key:
            next_api_key = api_key.strip() if api_key and api_key.strip() else None
        next_oi_source = current.oi_source
        if oi_source is not None:
            next_oi_source = _normalize_oi_source(oi_source, DEFAULT_OI_SOURCE, strict=True)

        updated = replace(
            current,
            enabled=enabled,
            api_key=next_api_key,
            oi_source=next_oi_source,
            sources=normalized_sources,
            refresh_interval_seconds=refresh_interval_seconds,
            volatility_threshold_pct=volatility_threshold_pct if volatility_threshold_pct is not None else current.volatility_threshold_pct,
            last_fetch_at=None,
            last_success_at=None,
            last_success_assets=None,
        )
        return await self._repository.upsert(updated)

    async def resolve_assets(self, force_refresh: bool = False) -> DynamicAssetsState:
        config = await self.get_config()
        binance_active = await self._is_binance_active()

        if not config.enabled or not binance_active:
            return DynamicAssetsState(
                assets=[],
                enabled=config.enabled,
                binance_active=binance_active,
                is_stale=False,
                last_success_at=config.last_success_at,
                last_fetch_at=config.last_fetch_at,
            )

        now = datetime.now(timezone.utc)
        config = await self._maybe_refresh(config, now, force_refresh)

        assets: list[str] = []
        is_stale = False
        if config.last_success_assets and config.last_success_at:
            age = (now - config.last_success_at).total_seconds()
            if age <= MAX_STALE_SECONDS:
                assets = list(config.last_success_assets)
            else:
                is_stale = True

        return DynamicAssetsState(
            assets=assets,
            enabled=config.enabled,
            binance_active=binance_active,
            is_stale=is_stale,
            last_success_at=config.last_success_at,
            last_fetch_at=config.last_fetch_at,
        )

    async def test_fetch(
        self,
        sources: Dict[str, Any],
        api_key: Optional[str] = None,
    ) -> list[str]:
        config = await self.get_config()
        key = api_key if api_key is not None else config.api_key
        normalized_sources = _normalize_sources(sources)
        normalized_sources = _strip_ai_sources_if_custom(normalized_sources, config.oi_source)
        client = self._select_client(config.oi_source)
        if client is self._nofx_client and not key:
            return []
        return await client.fetch_multi_source_assets(normalized_sources, key)

    async def is_binance_active(self) -> bool:
        return await self._is_binance_active()

    async def _maybe_refresh(
        self,
        config: DynamicAssetsConfig,
        now: datetime,
        force_refresh: bool = False,
    ) -> DynamicAssetsConfig:
        refresh_interval = config.refresh_interval_seconds or DEFAULT_REFRESH_INTERVAL_SECONDS
        if config.last_fetch_at is not None:
            elapsed = (now - config.last_fetch_at).total_seconds()
            if not force_refresh and elapsed < refresh_interval:
                return config

        assets: list[str] = []
        try:
            client = self._select_client(config.oi_source)
            sources = _strip_ai_sources_if_custom(config.sources, config.oi_source)
            assets = await client.fetch_multi_source_assets(sources, config.api_key)
        except Exception as exc:
            logger.warning("Dynamic assets fetch failed: %s", exc)

        if assets:
            assets = _filter_excluded_assets(assets, config.sources)
            assets = _normalize_assets(assets)
            assets = await self._exclude_open_positions(assets)
            assets, removed = await self._filter_extreme_24h_change(assets, config.volatility_threshold_pct)
            self._last_removed_high_volatility = removed
            self._last_volatility_checked_at = now

        updated = replace(config, last_fetch_at=now)
        if assets:
            updated = replace(
                updated,
                last_success_assets=assets,
                last_success_at=now,
            )

        return await self._repository.upsert(updated)

    async def _is_binance_active(self) -> bool:
        try:
            account = await self._portfolio_service.get_active_account()
        except Exception:
            return False
        if not account:
            return False
        return account.exchange.lower() == "binance"

    async def _exclude_open_positions(self, assets: Iterable[str]) -> list[str]:
        assets_list = list(assets)
        try:
            snapshot = await self._portfolio_service.get_portfolio_snapshot()
        except Exception:
            return assets_list

        open_symbols = {_normalize_asset(pos.symbol) for pos in snapshot.positions if pos.symbol}
        if not open_symbols:
            return assets_list

        filtered = [asset for asset in assets_list if _normalize_asset(asset) not in open_symbols]
        if len(filtered) != len(assets_list):
            logger.info("Dynamic assets: removed %s open positions", len(assets_list) - len(filtered))
        return filtered

    async def _filter_extreme_24h_change(
        self, assets: Iterable[str], threshold_pct: float = DEFAULT_24H_CHANGE_PCT
    ) -> tuple[list[str], list[str]]:
        assets_list = list(assets)
        if not assets_list:
            return assets_list, []

        try:
            change_map = await asyncio.to_thread(
                self._binance_client.fetch_24h_change_pct,
                assets_list,
            )
        except Exception as exc:
            logger.warning("Dynamic assets 24h change filter failed: %s", exc)
            return assets_list, []

        if not change_map:
            error = self._binance_client.consume_last_error()
            if error:
                logger.warning("Dynamic assets 24h change unavailable: %s", error)
            return assets_list, []

        filtered: list[str] = []
        removed_assets: list[str] = []
        for asset in assets_list:
            change = change_map.get(asset)
            if change is None:
                filtered.append(asset)
                continue
            if abs(change) >= threshold_pct:
                removed_assets.append(asset)
                continue
            filtered.append(asset)
        if removed_assets:
            logger.info(
                "Dynamic assets: removed %s tickers over %s%% 24h change",
                len(removed_assets),
                threshold_pct,
            )
        return filtered, removed_assets

    def get_last_removed_high_volatility(self) -> list[str]:
        return list(self._last_removed_high_volatility)

    def get_last_volatility_checked_at(self) -> Optional[datetime]:
        return self._last_volatility_checked_at

    def _default_config(self) -> DynamicAssetsConfig:
        return DynamicAssetsConfig(
            enabled=False,
            api_key=None,
            oi_source=self._default_oi_source,
            sources=_normalize_sources({}),
            refresh_interval_seconds=DEFAULT_REFRESH_INTERVAL_SECONDS,
            volatility_threshold_pct=DEFAULT_24H_CHANGE_PCT,
        )

    def _normalize_config(self, config: DynamicAssetsConfig) -> DynamicAssetsConfig:
        sources = _normalize_sources(config.sources or {})
        refresh_interval = config.refresh_interval_seconds or DEFAULT_REFRESH_INTERVAL_SECONDS
        oi_source = _normalize_oi_source(config.oi_source, self._default_oi_source)
        return replace(
            config,
            oi_source=oi_source,
            sources=sources,
            refresh_interval_seconds=refresh_interval,
        )

    def _select_client(self, oi_source: str) -> NofXOSDynamicAssetsClient | OiRankDynamicAssetsClient:
        if oi_source == "custom":
            return self._oi_rank_client
        return self._nofx_client


def _normalize_sources(sources: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    normalized = {key: dict(value) for key, value in DEFAULT_SOURCES.items()}
    for key, value in sources.items():
        if key not in normalized or not isinstance(value, dict):
            continue
        normalized[key].update(value)
    for key, value in normalized.items():
        value["enabled"] = bool(value.get("enabled", False))
        if "limit" in value:
            try:
                value["limit"] = max(1, int(value.get("limit", 1)))
            except (TypeError, ValueError):
                value["limit"] = DEFAULT_SOURCES[key]["limit"]
        if key == "excluded_assets":
            value["enabled"] = False
            value["symbols"] = _normalize_excluded_symbols(value.get("symbols", ""))
    return normalized


def _strip_ai_sources_if_custom(
    sources: Dict[str, Dict[str, Any]],
    oi_source: str,
) -> Dict[str, Dict[str, Any]]:
    if oi_source != "custom":
        return sources
    stripped = {key: dict(value) for key, value in sources.items()}
    for key in ("ai500", "ai300", "netflow_top", "netflow_low", "futures_depth"):
        if key in stripped:
            stripped[key]["enabled"] = False
    return stripped


def _filter_excluded_assets(assets: Iterable[str], sources: Dict[str, Dict[str, Any]]) -> list[str]:
    assets_list = list(assets)
    excluded = _extract_excluded_assets(sources)
    if not assets_list or not excluded:
        return assets_list

    filtered: list[str] = []
    removed = 0
    for asset in assets_list:
        normalized = _normalize_asset(asset)
        if normalized and normalized in excluded:
            removed += 1
            continue
        filtered.append(asset)

    if removed > 0:
        logger.info("Dynamic assets: removed %s user-excluded tickers", removed)
    return filtered


def _extract_excluded_assets(sources: Dict[str, Dict[str, Any]]) -> set[str]:
    if not isinstance(sources, dict):
        return set()
    entry = sources.get("excluded_assets")
    if not isinstance(entry, dict):
        return set()
    normalized = _normalize_excluded_symbols(entry.get("symbols", ""))
    if not normalized:
        return set()
    return {item for item in normalized.split(",") if item}


def _normalize_excluded_symbols(value: Any) -> str:
    if isinstance(value, str):
        candidates = value.split(",")
    elif isinstance(value, list):
        candidates = [str(item) for item in value]
    elif value is None:
        candidates = []
    else:
        candidates = [str(value)]

    ordered: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = _normalize_asset(candidate)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ",".join(ordered)


def _normalize_oi_source(value: Optional[str], default: str, strict: bool = False) -> str:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in SUPPORTED_OI_SOURCES:
        return normalized
    if strict:
        raise AppError(
            code="dynamic_assets_invalid_oi_source",
            message="OI source must be either nofx or custom.",
        )
    return default


def _normalize_assets(assets: Iterable[str]) -> list[str]:
    normalized = {_normalize_asset(asset) for asset in assets if _normalize_asset(asset)}
    return sorted(normalized)


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
