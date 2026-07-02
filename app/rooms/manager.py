from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.db.models import Room, RoomPlayer
from app.game.runtime import RoomConfig, RoomRuntime


class RoomManager:
    def __init__(self) -> None:
        self._runtimes: dict[str, RoomRuntime] = {}

    def get_or_create(self, room: Room) -> RoomRuntime:
        runtime = self._runtimes.get(room.code)
        if runtime is None:
            runtime = RoomRuntime(
                RoomConfig(
                    room_id=room.id,
                    code=room.code,
                    name=room.name,
                    seat_count=room.seat_count,
                    small_blind=room.small_blind,
                    big_blind=room.big_blind,
                    buy_in=room.buy_in,
                )
            )
            self._runtimes[room.code] = runtime
        return runtime

    def remove(self, room_code: str) -> RoomRuntime | None:
        return self._runtimes.pop(room_code.upper(), None)

    def sync_from_db(self, db: DbSession, room: Room) -> RoomRuntime:
        runtime = self.get_or_create(room)
        if runtime.phase != "waiting":
            return runtime

        room_players = db.execute(
            select(RoomPlayer).where(RoomPlayer.room_id == room.id, RoomPlayer.left_at.is_(None))
        ).scalars()
        active_seats: set[int] = set()
        for room_player in room_players:
            if room_player.seat_index is None:
                continue
            runtime.sync_seated_player(
                room_player.user_id,
                room_player.user.username,
                room_player.seat_index,
                room_player.player_type,
            )
            active_seats.add(room_player.seat_index)

        for seat in list(runtime.players):
            if seat not in active_seats:
                del runtime.players[seat]
        return runtime
