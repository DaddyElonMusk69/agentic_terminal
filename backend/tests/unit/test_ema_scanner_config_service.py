import pytest

from app.application.ema_scanner.config_service import EmaScannerConfigService
from app.domain.ema_scanner.models import EmaScannerLine


class StubAssetsService:
    async def list_assets(self, include_positions: bool = True, force_refresh: bool = False):
        del include_positions, force_refresh
        return ["BTC", "ETH"]


class StubEmaScannerRepository:
    def __init__(self):
        self.tolerance = 0.2
        self.scan_intervals = None
        self.monitored_intervals = ["1h", "2h", "4h"]

    async def get_tolerance(self):
        return self.tolerance

    async def set_tolerance(self, value: float):
        self.tolerance = value
        return value

    async def get_scan_intervals(self):
        return self.scan_intervals

    async def set_scan_intervals(self, intervals):
        self.scan_intervals = intervals
        return intervals

    async def list_ema_lines(self):
        return [144, 169]

    async def list_ema_line_records(self):
        return [EmaScannerLine(id=1, length=144), EmaScannerLine(id=2, length=169)]

    async def add_ema_line(self, length: int):
        return [EmaScannerLine(id=1, length=length)]

    async def remove_ema_line(self, line_id: int):
        del line_id
        return []

    async def list_monitored_coins(self):
        return []

    async def list_monitored_assets(self):
        return []

    async def list_monitored_intervals(self):
        return list(self.monitored_intervals)


@pytest.mark.asyncio
async def test_build_config_defaults_to_all_monitored_intervals():
    repository = StubEmaScannerRepository()
    service = EmaScannerConfigService(repository, StubAssetsService())

    config = await service.build_config()

    assert config.assets == ["BTC", "ETH"]
    assert config.timeframes == ["1h", "2h", "4h"]


@pytest.mark.asyncio
async def test_update_scan_intervals_filters_to_monitored_subset():
    repository = StubEmaScannerRepository()
    service = EmaScannerConfigService(repository, StubAssetsService())

    selected = await service.update_scan_intervals(["4h", "15m", "1h"])

    assert selected == ["1h", "4h"]
    assert repository.scan_intervals == ["1h", "4h"]


@pytest.mark.asyncio
async def test_update_scan_intervals_stores_none_when_all_monitored_selected():
    repository = StubEmaScannerRepository()
    service = EmaScannerConfigService(repository, StubAssetsService())

    selected = await service.update_scan_intervals(["4h", "2h", "1h"])

    assert selected == ["1h", "2h", "4h"]
    assert repository.scan_intervals is None


@pytest.mark.asyncio
async def test_effective_scan_intervals_fall_back_when_configured_subset_is_stale():
    repository = StubEmaScannerRepository()
    repository.scan_intervals = ["12h"]
    service = EmaScannerConfigService(repository, StubAssetsService())

    intervals = await service.get_effective_scan_intervals()

    assert intervals == ["1h", "2h", "4h"]
