from __future__ import annotations

from urllib.parse import urlparse

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.auth.security import get_session_by_token
from app.config import settings
from app.db.models import Room
from app.db.session import SessionLocal
from app.game.runtime import GameError

router = APIRouter()


@router.websocket("/ws/rooms/{code}")
async def room_socket(websocket: WebSocket, code: str) -> None:
    if not _origin_allowed(websocket):
        await websocket.close(code=1008)
        return

    db = SessionLocal()
    user = None
    room = None
    try:
        session = get_session_by_token(db, websocket.cookies.get(settings.session_cookie_name))
        if session is None:
            await websocket.close(code=1008)
            return
        user = session.user
        room = db.execute(select(Room).where(Room.code == code.upper())).scalar_one_or_none()
        if room is None:
            await websocket.close(code=1008)
            return

        service = websocket.app.state.game_service
        connections = websocket.app.state.connection_manager
        runtime = await service.sync_room(db, room)
        async with runtime.lock:
            runtime.set_connected(user.id, True)
        await connections.connect(room.code, user.id, websocket)
        await websocket.send_json({"type": "state.snapshot", "payload": runtime.public_state(user.id)})

        while True:
            message = await websocket.receive_json()
            await _handle_message(websocket, db, room, user, message)
    except WebSocketDisconnect:
        pass
    finally:
        if user is not None and room is not None:
            service = websocket.app.state.game_service
            connections = websocket.app.state.connection_manager
            connections.disconnect(room.code, user.id, websocket)
            room_exists = db.execute(select(Room.id).where(Room.id == room.id)).scalar_one_or_none()
            if room_exists is not None:
                runtime = service.room_manager.get_or_create(room)
                async with runtime.lock:
                    runtime.set_connected(user.id, False)
                await connections.broadcast_state(runtime)
        db.close()


async def _handle_message(websocket: WebSocket, db, room: Room, user, message: dict) -> None:
    service = websocket.app.state.game_service
    connections = websocket.app.state.connection_manager
    message_type = message.get("type")
    payload = message.get("payload") or {}
    request_id = message.get("request_id")

    try:
        if message_type == "ping":
            await websocket.send_json({"type": "pong", "request_id": request_id, "payload": {}})
            return
        if message_type == "seat.take":
            await service.take_seat(db, room, user, int(payload.get("seat_index")))
        elif message_type == "seat.leave":
            await service.stand(db, room, user)
        elif message_type == "room.ready":
            await service.set_ready(room, user, bool(payload.get("ready", True)))
        elif message_type == "hand.start":
            await service.start_hand(room, user)
        elif message_type == "hand.action":
            action_type = payload.get("action_type") or payload.get("type")
            amount = int(payload.get("amount") or 0)
            await service.submit_action(room, user, action_type, amount)
        elif message_type == "bot.add":
            await service.add_bot(
                room,
                user,
                int(payload.get("seat_index")),
                str(payload.get("strategy") or ""),
                str(payload.get("variant") or "") or None,
            )
        elif message_type == "bot.remove":
            await service.remove_bot(room, user, int(payload.get("seat_index")))
        elif message_type == "phrase.send":
            await service.send_phrase(room, user, str(payload.get("text") or ""))
        else:
            raise GameError("不支持的消息类型。")
        await websocket.send_json({"type": "action.accepted", "request_id": request_id, "payload": {}})
    except (GameError, TypeError, ValueError) as exc:
        await connections.send_to_user(room.code, user.id, {"type": "error", "request_id": request_id, "payload": {"message": str(exc)}})


def _origin_allowed(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin")
    if not origin:
        return True
    if "*" in settings.allowed_origins or origin in settings.allowed_origins:
        return True
    if settings.allowed_origins:
        return False
    origin_host = urlparse(origin).netloc
    request_host = websocket.headers.get("host")
    return bool(origin_host and request_host and origin_host == request_host)
