from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.db.models import Room, RoomPlayer, User
from app.game.runtime import GameError, RoomRuntime
from app.realtime.manager import ConnectionManager
from app.rooms.manager import RoomManager


class GameService:
    def __init__(self, room_manager: RoomManager, connections: ConnectionManager) -> None:
        self.room_manager = room_manager
        self.connections = connections

    async def sync_room(self, db: DbSession, room: Room) -> RoomRuntime:
        runtime = self.room_manager.get_or_create(room)
        async with runtime.lock:
            runtime = self.room_manager.sync_from_db(db, room)
        await self.connections.broadcast_state(runtime)
        return runtime

    async def take_seat(self, db: DbSession, room: Room, user: User, seat_index: int) -> RoomRuntime:
        runtime = self.room_manager.get_or_create(room)
        async with runtime.lock:
            existing = db.execute(
                select(RoomPlayer).where(
                    RoomPlayer.room_id == room.id,
                    RoomPlayer.seat_index == seat_index,
                    RoomPlayer.left_at.is_(None),
                    RoomPlayer.user_id != user.id,
                )
            ).scalar_one_or_none()
            if existing is not None:
                raise GameError("该座位已被占用。")
            runtime.seat_player(user.id, user.username, seat_index)
            room_player = _get_or_create_room_player(db, room, user)
            room_player.seat_index = seat_index
            room_player.left_at = None
            db.commit()
        await self.connections.broadcast_state(runtime)
        return runtime

    async def stand(self, db: DbSession, room: Room, user: User) -> RoomRuntime:
        runtime = self.room_manager.get_or_create(room)
        async with runtime.lock:
            runtime.stand_player(user.id)
            room_player = _get_room_player(db, room, user)
            if room_player is not None:
                room_player.seat_index = None
                db.commit()
        await self.connections.broadcast_state(runtime)
        return runtime

    async def set_ready(self, room: Room, user: User, ready: bool = True) -> RoomRuntime:
        runtime = self.room_manager.get_or_create(room)
        async with runtime.lock:
            runtime.set_ready(user.id, ready)
            if ready and runtime.can_start_hand():
                runtime.start_hand()
        await self.connections.broadcast_state(runtime)
        return runtime

    async def start_hand(self, room: Room, user: User) -> RoomRuntime:
        runtime = self.room_manager.get_or_create(room)
        async with runtime.lock:
            if runtime.phase != "waiting":
                raise GameError("当前手牌尚未结束。")
            starter = next((player for player in runtime.players.values() if player.user_id == user.id), None)
            if starter is None:
                raise GameError("请先入座再开始手牌。")
            if not starter.ready or starter.stack <= 0:
                raise GameError("请先准备再开始手牌。")
            runtime.start_hand()
        await self.connections.broadcast_state(runtime)
        return runtime

    async def submit_action(self, room: Room, user: User, action_type: str, amount: int = 0) -> RoomRuntime:
        runtime = self.room_manager.get_or_create(room)
        async with runtime.lock:
            runtime.submit_action(user.id, action_type, amount)
        await self.connections.broadcast_state(runtime)
        return runtime

    async def send_phrase(self, room: Room, user: User, text: str) -> RoomRuntime:
        runtime = self.room_manager.get_or_create(room)
        async with runtime.lock:
            phrase = runtime.send_phrase(user.id, text)
        await self.connections.broadcast_room(
            runtime.code,
            {"type": "phrase.sent", "payload": phrase.to_public()},
        )
        return runtime


def _get_room_player(db: DbSession, room: Room, user: User) -> RoomPlayer | None:
    return db.execute(
        select(RoomPlayer).where(RoomPlayer.room_id == room.id, RoomPlayer.user_id == user.id)
    ).scalar_one_or_none()


def _get_or_create_room_player(db: DbSession, room: Room, user: User) -> RoomPlayer:
    room_player = _get_room_player(db, room, user)
    if room_player is None:
        room_player = RoomPlayer(room_id=room.id, user_id=user.id, player_type="human")
        db.add(room_player)
        db.flush()
    return room_player
