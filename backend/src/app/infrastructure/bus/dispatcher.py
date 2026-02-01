from app.application.bus.interfaces import MessagePublisher
from app.infrastructure.bus.outbox_repository import OutboxRepository


class OutboxDispatcher:
    def __init__(self, repository: OutboxRepository, publisher: MessagePublisher) -> None:
        self._repository = repository
        self._publisher = publisher

    async def dispatch(self, limit: int = 100) -> int:
        messages = await self._repository.get_pending(limit)
        dispatched = 0

        for message in messages:
            try:
                await self._publisher.publish(message)
                await self._repository.mark_processed(message.id)
                dispatched += 1
            except Exception as exc:  # pragma: no cover - depends on publisher
                await self._repository.mark_failed(message.id, str(exc))

        return dispatched
