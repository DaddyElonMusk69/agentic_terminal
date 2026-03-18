import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.infrastructure.db.models import Base
from app.infrastructure.db.models.prompt_build_queue import PromptBuildRequestModel
from app.infrastructure.repositories.prompt_build_queue_repository import PromptBuildQueueRepository


@pytest.mark.asyncio
async def test_delete_by_statuses_purges_only_matching_prompt_requests():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    repository = PromptBuildQueueRepository(sessionmaker)
    await repository.enqueue("queued-1", {"symbol": "BTCUSDT"}, None)
    await repository.enqueue("queued-2", {"symbol": "ETHUSDT"}, None)
    await repository.enqueue("done-1", {"symbol": "SOLUSDT"}, None)
    await repository.mark_done("done-1", {"ok": True})

    purged = await repository.delete_by_statuses(["queued"])

    assert purged == 2

    async with sessionmaker() as session:
        remaining = (
            await session.execute(
                select(PromptBuildRequestModel.id, PromptBuildRequestModel.status).order_by(
                    PromptBuildRequestModel.id
                )
            )
        ).all()

    assert remaining == [("done-1", "done")]
