from app.application.bus.models import OutboxMessage
from app.application.bus.interfaces import MessagePublisher
from app.realtime.hub import RealtimeHub


class SocketIOPublisher(MessagePublisher):
    def __init__(self, hub: RealtimeHub) -> None:
        self._hub = hub

    async def publish(self, message: OutboxMessage) -> None:
        await self._hub.emit_topic(
            topic=message.topic,
            payload=message.payload,
            request_id=message.id,
        )
