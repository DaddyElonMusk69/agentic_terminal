import pytest
import socketio

from app.realtime import events


@pytest.mark.asyncio
async def test_ping_handler_envelope():
    sio = socketio.AsyncServer(async_mode="asgi")
    events.register_handlers(sio)

    handler = sio.handlers["/"].get("ping")
    assert handler is not None

    payload = await handler("sid-1", {"hello": "world"})

    assert payload["v"] == 1
    assert payload["type"] == "event"
    assert payload["topic"] == "system.pong"
    assert payload["payload"]["sid"] == "sid-1"
    assert payload["payload"]["echo"] == {"hello": "world"}
    assert "ts" in payload
