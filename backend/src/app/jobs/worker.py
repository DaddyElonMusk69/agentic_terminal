from taskiq_redis import ListQueueBroker

from app.infrastructure.bus.dispatcher import OutboxDispatcher
from app.infrastructure.bus.outbox_repository import OutboxRepository
from app.infrastructure.bus.redis_publisher import RedisMessagePublisher
from app.infrastructure.db import get_sessionmaker
from app.application.prompt_builder.dependencies import get_prompt_builder_service
from app.application.prompt_builder.queue_worker import PromptBuildQueueWorker
from app.application.automation.dependencies import (
    get_automation_pipeline_service,
    get_prompt_pipeline_worker,
    get_llm_queue_worker,
    get_order_queue_worker,
)
from app.infrastructure.repositories.prompt_build_queue_repository import PromptBuildQueueRepository
from app.settings import get_settings

settings = get_settings()

broker = ListQueueBroker(settings.redis_url)


@broker.task
async def dispatch_outbox(limit: int = 100) -> dict:
    repository = OutboxRepository(get_sessionmaker())
    publisher = RedisMessagePublisher(settings.redis_url)
    dispatcher = OutboxDispatcher(repository, publisher)

    count = await dispatcher.dispatch(limit)
    await publisher.close()

    return {"dispatched": count}


@broker.task
async def process_prompt_build_queue(limit: int = 1) -> dict:
    repository = PromptBuildQueueRepository(get_sessionmaker())
    worker = PromptBuildQueueWorker(repository, get_prompt_builder_service())

    processed = 0
    for _ in range(max(limit, 1)):
        handled = await worker.process_next()
        if not handled:
            break
        processed += 1

    return {"processed": processed}


@broker.task
async def run_ema_scan_once() -> dict:
    pipeline = get_automation_pipeline_service()
    return await pipeline.run_ema_cycle()


@broker.task
async def run_quant_scan_once(limit: int = 200) -> dict:
    pipeline = get_automation_pipeline_service()
    return await pipeline.run_quant_cycle(limit=limit)


@broker.task
async def process_prompt_pipeline_queue(limit: int = 1) -> dict:
    worker = get_prompt_pipeline_worker()
    processed = 0
    for _ in range(max(limit, 1)):
        handled = await worker.process_next()
        if not handled:
            break
        processed += 1
    return {"processed": processed}


@broker.task
async def process_llm_queue(limit: int = 1) -> dict:
    worker = get_llm_queue_worker()
    processed = 0
    for _ in range(max(limit, 1)):
        handled = await worker.process_next()
        if not handled:
            break
        processed += 1
    return {"processed": processed}


@broker.task
async def process_order_queue(limit: int = 1) -> dict:
    worker = get_order_queue_worker()
    processed = 0
    for _ in range(max(limit, 1)):
        handled = await worker.process_next()
        if not handled:
            break
        processed += 1
    return {"processed": processed}
