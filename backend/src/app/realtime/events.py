from typing import Any, Dict

import socketio

from app.realtime.envelope import build_envelope
from app.realtime.topics import normalize_topics, topic_room


def register_handlers(sio: socketio.AsyncServer) -> None:
    @sio.event
    async def connect(sid: str, environ: Dict[str, Any], auth: Dict[str, Any] | None) -> bool:
        await sio.emit(
            "event",
            build_envelope("system.hello", {"sid": sid}),
            to=sid,
        )
        return True

    @sio.event
    async def disconnect(sid: str) -> None:
        return None

    @sio.event
    async def ping(sid: str, data: Dict[str, Any] | None = None) -> None:
        await sio.emit(
            "event",
            build_envelope("system.pong", {"sid": sid, "echo": data or {}}),
            to=sid,
        )

    @sio.event
    async def subscribe(sid: str, data: Dict[str, Any] | None = None) -> None:
        topics = normalize_topics(data or {})
        if not topics:
            await sio.emit(
                "event",
                build_envelope("system.error", {"message": "no_topics"}),
                to=sid,
            )
            return

        for topic in topics:
            await sio.enter_room(sid, topic_room(topic))

        await sio.emit(
            "event",
            build_envelope("system.subscribed", {"topics": topics}),
            to=sid,
        )

    @sio.event
    async def unsubscribe(sid: str, data: Dict[str, Any] | None = None) -> None:
        topics = normalize_topics(data or {})
        if not topics:
            await sio.emit(
                "event",
                build_envelope("system.error", {"message": "no_topics"}),
                to=sid,
            )
            return

        for topic in topics:
            await sio.leave_room(sid, topic_room(topic))

        await sio.emit(
            "event",
            build_envelope("system.unsubscribed", {"topics": topics}),
            to=sid,
        )
