from typing import Protocol

from app.application.bus.models import OutboxMessage


class MessagePublisher(Protocol):
    async def publish(self, message: OutboxMessage) -> None:
        ...
