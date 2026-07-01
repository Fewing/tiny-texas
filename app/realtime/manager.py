from __future__ import annotations

from collections import defaultdict

from fastapi import WebSocket

from app.game.runtime import RoomRuntime


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, dict[int, set[WebSocket]]] = defaultdict(lambda: defaultdict(set))

    async def connect(self, room_code: str, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[room_code][user_id].add(websocket)

    def disconnect(self, room_code: str, user_id: int, websocket: WebSocket) -> None:
        user_connections = self._connections.get(room_code, {}).get(user_id)
        if not user_connections:
            return
        user_connections.discard(websocket)
        if not user_connections:
            self._connections[room_code].pop(user_id, None)
        if not self._connections.get(room_code):
            self._connections.pop(room_code, None)

    async def send_to_user(self, room_code: str, user_id: int, message: dict) -> None:
        dead: list[WebSocket] = []
        for websocket in self._connections.get(room_code, {}).get(user_id, set()):
            try:
                await websocket.send_json(message)
            except RuntimeError:
                dead.append(websocket)
        for websocket in dead:
            self.disconnect(room_code, user_id, websocket)

    async def broadcast_state(self, runtime: RoomRuntime) -> None:
        for user_id in list(self._connections.get(runtime.code, {})):
            await self.send_to_user(
                runtime.code,
                user_id,
                {"type": "state.snapshot", "payload": runtime.public_state(user_id)},
            )

    async def broadcast_error(self, room_code: str, user_id: int, message: str) -> None:
        await self.send_to_user(room_code, user_id, {"type": "error", "payload": {"message": message}})

