from typing import Any, Dict, Optional

import socketio

from app.realtime.envelope import build_envelope
from app.realtime.topics import topic_room, topic_rooms_for


class RealtimeHub:
    def __init__(self) -> None:
        self._sio: Optional[socketio.AsyncServer] = None

    def bind(self, sio: socketio.AsyncServer) -> None:
        self._sio = sio

    async def emit_event(
        self,
        topic: str,
        payload: Dict[str, Any],
        request_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        room: Optional[str] = None,
        to: Optional[str] = None,
    ) -> None:
        if self._sio is None:
            return
        envelope = build_envelope(
            topic=topic,
            payload=payload,
            request_id=request_id,
            trace_id=trace_id,
        )
        if room:
            await self._sio.emit("event", envelope, room=room)
            return
        if to:
            await self._sio.emit("event", envelope, to=to)
            return
        await self._sio.emit("event", envelope)

    async def emit_topic(
        self,
        topic: str,
        payload: Dict[str, Any],
        request_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> None:
        rooms = topic_rooms_for(topic)
        for room in rooms:
            await self.emit_event(
                topic=topic,
                payload=payload,
                request_id=request_id,
                trace_id=trace_id,
                room=room,
            )


hub = RealtimeHub()
