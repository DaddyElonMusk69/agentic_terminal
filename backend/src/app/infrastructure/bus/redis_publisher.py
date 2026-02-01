import json
from typing import Any, Dict

from redis.asyncio import Redis

from app.application.bus.models import OutboxMessage


class RedisMessagePublisher:
    def __init__(self, redis_url: str) -> None:
        self._redis = Redis.from_url(redis_url)

    async def publish(self, message: OutboxMessage) -> None:
        payload: Dict[str, Any] = {
            "id": message.id,
            "type": message.message_type,
            "topic": message.topic,
            "payload": message.payload,
            "created_at": message.created_at.isoformat(),
        }
        await self._redis.publish(message.topic, json.dumps(payload))

    async def close(self) -> None:
        await self._redis.close()
