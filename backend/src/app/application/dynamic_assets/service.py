from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import logging
from typing import Any, Dict, Optional

from app.common.errors import AppError
from app.domain.dynamic_assets.models import DynamicAssetsConfig, DynamicAssetsState
from app.domain.dynamic_assets.interfaces import DynamicAssetsConfigRepository
from app.infrastructure.external.nofxos_dynamic_assets import NofXOSDynamicAssetsClient
from app.application.portfolio.service import PortfolioService


logger = logging.getLogger(__name__)

DEFAULT_REFRESH_INTERVAL_SECONDS = 600
MIN_REFRESH_INTERVAL_SECONDS = 60
MAX_REFRESH_INTERVAL_SECONDS = 3600
MAX_STALE_SECONDS = 1800

DEFAULT_SOURCES: Dict[str, Dict[str, Any]] = {
    "ai500": {"enabled": False, "limit": 10},
    "ai300": {"enabled": False, "limit": 20, "level": ""},
    "oi_top": {"enabled": False, "limit": 20, "duration": "1h"},
    "oi_low": {"enabled": False, "limit": 20, "duration": "1h"},
}


class DynamicAssetsService:
    def __init__(
        self,
        repository: DynamicAssetsConfigRepository,
        portfolio_service: PortfolioService,
        client: Optional[NofXOSDynamicAssetsClient] = None,
    ) -> None:
        self._repository = repository
        self._portfolio_service = portfolio_service
        self._client = client or NofXOSDynamicAssetsClient()

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
        api_key: Optional[str] = None,
        update_api_key: bool = False,
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

        updated = replace(
            current,
            enabled=enabled,
            api_key=next_api_key,
            sources=normalized_sources,
            refresh_interval_seconds=refresh_interval_seconds,
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
        if not key:
            return []
        normalized_sources = _normalize_sources(sources)
        return await self._client.fetch_multi_source_assets(normalized_sources, key)

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

        assets = []
        try:
            assets = await self._client.fetch_multi_source_assets(config.sources, config.api_key)
        except Exception as exc:
            logger.warning("Dynamic assets fetch failed: %s", exc)

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

    def _default_config(self) -> DynamicAssetsConfig:
        return DynamicAssetsConfig(
            enabled=False,
            api_key=None,
            sources=_normalize_sources({}),
            refresh_interval_seconds=DEFAULT_REFRESH_INTERVAL_SECONDS,
        )

    def _normalize_config(self, config: DynamicAssetsConfig) -> DynamicAssetsConfig:
        sources = _normalize_sources(config.sources or {})
        refresh_interval = config.refresh_interval_seconds or DEFAULT_REFRESH_INTERVAL_SECONDS
        return replace(
            config,
            sources=sources,
            refresh_interval_seconds=refresh_interval,
        )


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
    return normalized
