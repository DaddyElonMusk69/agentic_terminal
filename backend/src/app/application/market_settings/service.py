from typing import List

from app.domain.market_settings.interfaces import MarketSettingsRepository


DEFAULT_ASSETS = ["BTC"]
DEFAULT_INTERVALS: List[str] = []


class MarketSettingsService:
    def __init__(self, repository: MarketSettingsRepository) -> None:
        self._repository = repository

    async def list_assets(self) -> List[str]:
        assets = await self._repository.list_assets()
        if not assets:
            for symbol in DEFAULT_ASSETS:
                await self._repository.add_asset(symbol)
            assets = await self._repository.list_assets()
        return assets

    async def list_intervals(self) -> List[str]:
        intervals = await self._repository.list_intervals()
        if not intervals:
            for interval in DEFAULT_INTERVALS:
                await self._repository.add_interval(interval)
            intervals = await self._repository.list_intervals()
        return intervals

    async def add_asset(self, symbol: str) -> List[str]:
        normalized = symbol.strip().upper()
        if normalized:
            await self._repository.add_asset(normalized)
        return await self.list_assets()

    async def remove_asset(self, symbol: str) -> List[str]:
        normalized = symbol.strip().upper()
        if normalized:
            await self._repository.remove_asset(normalized)
        return await self.list_assets()

    async def add_interval(self, interval: str) -> List[str]:
        normalized = interval.strip().lower()
        if normalized:
            await self._repository.add_interval(normalized)
        return await self.list_intervals()

    async def remove_interval(self, interval: str) -> List[str]:
        normalized = interval.strip().lower()
        if normalized:
            await self._repository.remove_interval(normalized)
        return await self.list_intervals()
