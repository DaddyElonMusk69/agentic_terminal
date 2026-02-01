import socketio

from app.realtime.events import register_handlers
from app.realtime.hub import hub


def create_socketio_server(cors_origins: str | list[str]) -> socketio.AsyncServer:
    sio = socketio.AsyncServer(
        async_mode="asgi",
        cors_allowed_origins=cors_origins,
    )
    hub.bind(sio)
    register_handlers(sio)
    return sio


def create_socketio_app(
    sio: socketio.AsyncServer,
    other_asgi_app,
    socketio_path: str,
):
    return socketio.ASGIApp(
        sio,
        other_asgi_app=other_asgi_app,
        socketio_path=socketio_path.lstrip("/"),
    )
