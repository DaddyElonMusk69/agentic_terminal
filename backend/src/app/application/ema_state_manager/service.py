from typing import List, Sequence

from app.application.ema_state_manager.config_service import EmaStateManagerConfigService
from app.domain.ema_scanner.models import EmaScannerSignal
from app.domain.ema_state_manager.models import (
    EmaStateEvent,
    EmaStateManagerConfig,
    PositionSnapshot,
)
from app.domain.ema_state_manager.service import EmaStateManager


class EmaStateManagerService:
    def __init__(
        self,
        config_service: EmaStateManagerConfigService,
        state_manager: EmaStateManager,
    ) -> None:
        self._config_service = config_service
        self._state_manager = state_manager

    async def process_signals(
        self,
        signals: Sequence[EmaScannerSignal],
        monitored_assets: Sequence[str],
        quote_asset: str = "USDT",
        open_positions: Sequence[PositionSnapshot] | None = None,
        update_assets: Sequence[str] | None = None,
        prune_missing: bool = True,
        state_config: EmaStateManagerConfig | None = None,
    ) -> List[EmaStateEvent]:
        config = state_config or await self._config_service.get_config()
        monitored_symbols = _normalize_assets(monitored_assets, quote_asset)
        update_symbols = (
            _normalize_assets(update_assets, quote_asset)
            if update_assets is not None
            else None
        )
        return self._state_manager.update(
            signals=signals,
            monitored_symbols=monitored_symbols,
            config=config,
            open_positions=open_positions,
            update_symbols=update_symbols,
            prune_missing=prune_missing,
        )

    async def get_config(self):
        return await self._config_service.get_config()

    def clear_state(self, symbol: str) -> None:
        self._state_manager.clear_state(symbol)

    def clear_all_states(self) -> None:
        self._state_manager.clear_all_states()

    def get_state(self, symbol: str):
        return self._state_manager.get_state(symbol)

    def get_all_states(self):
        return self._state_manager.get_all_states()


def _normalize_assets(assets: Sequence[str], quote_asset: str) -> List[str]:
    symbols: List[str] = []
    seen = set()

    for asset in assets:
        normalized = _normalize_symbol(asset, quote_asset)
        key = normalized.upper()
        if key in seen:
            continue
        seen.add(key)
        symbols.append(normalized)

    return symbols


def _normalize_symbol(asset: str, quote_asset: str) -> str:
    value = asset.strip().upper()
    if "/" in value or ":" in value:
        return value
    return f"{value}/{quote_asset}"
