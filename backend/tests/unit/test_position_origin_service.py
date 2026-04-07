from datetime import datetime, timezone

import pytest

from app.application.position_origin.service import PositionOriginService
from app.domain.position_origin.models import ActivePositionOriginRecord


class StubPositionOriginRepository:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], ActivePositionOriginRecord] = {}

    async def upsert(  # noqa: ANN001
        self,
        account_id,
        symbol,
        anchor_frame,
        active_tunnel,
        stop_loss_roe,
        take_profit_roe,
    ):
        now = datetime.now(timezone.utc)
        existing = self.rows.get((account_id, symbol))
        record = ActivePositionOriginRecord(
            account_id=account_id,
            symbol=symbol,
            anchor_frame=anchor_frame,
            active_tunnel=active_tunnel,
            stop_loss_roe=stop_loss_roe,
            take_profit_roe=take_profit_roe,
            created_at=existing.created_at if existing is not None else now,
            updated_at=now,
        )
        self.rows[(account_id, symbol)] = record
        return record

    async def get_many(self, account_id, symbols):  # noqa: ANN001
        return [self.rows[(account_id, symbol)] for symbol in symbols if (account_id, symbol) in self.rows]

    async def delete(self, account_id, symbol):  # noqa: ANN001
        return self.rows.pop((account_id, symbol), None) is not None

    async def prune_missing(self, account_id, live_symbols):  # noqa: ANN001
        keep = set(live_symbols)
        removed = 0
        for key in list(self.rows.keys()):
            row_account, row_symbol = key
            if row_account != account_id or row_symbol in keep:
                continue
            self.rows.pop(key, None)
            removed += 1
        return removed


@pytest.mark.asyncio
async def test_position_origin_service_preserves_existing_fields_on_partial_updates():
    repo = StubPositionOriginRepository()
    service = PositionOriginService(repo)

    created = await service.upsert(
        "acc-1",
        "BTC",
        "4h",
        "fast",
        stop_loss_roe=0.01,
        take_profit_roe=0.03,
    )
    assert created is not None

    updated_stop = await service.upsert(
        "acc-1",
        "BTC",
        stop_loss_roe=0.02,
    )
    assert updated_stop.anchor_frame == "4h"
    assert updated_stop.active_tunnel == "fast"
    assert updated_stop.stop_loss_roe == 0.02
    assert updated_stop.take_profit_roe == 0.03

    updated_tp = await service.upsert(
        "acc-1",
        "BTC",
        take_profit_roe=0.05,
    )
    assert updated_tp.anchor_frame == "4h"
    assert updated_tp.active_tunnel == "fast"
    assert updated_tp.stop_loss_roe == 0.02
    assert updated_tp.take_profit_roe == 0.05
