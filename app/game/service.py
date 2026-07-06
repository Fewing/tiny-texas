from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.bots import choose_bot_username, create_bot_strategy, normalize_bot_selection
from app.db.models import Room, RoomPlayer, User
from app.game.runtime import GameError, RoomRuntime, WAITING
from app.realtime.manager import ConnectionManager
from app.rooms.manager import RoomManager

BOT_ACTION_LIMIT = 50


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
            room_player.player_type = "human"
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
            self._ready_waiting_bots(runtime)
            if ready and self._can_auto_start(runtime):
                runtime.start_hand()
            await self._run_bot_turns_locked(runtime)
        await self.connections.broadcast_state(runtime)
        return runtime

    async def start_hand(self, room: Room, user: User) -> RoomRuntime:
        runtime = self.room_manager.get_or_create(room)
        async with runtime.lock:
            self._ready_waiting_bots(runtime)
            if runtime.phase != WAITING:
                raise GameError("当前手牌尚未结束。")
            starter = next((player for player in runtime.players.values() if player.user_id == user.id), None)
            if starter is None:
                raise GameError("请先入座再开始手牌。")
            if not starter.ready or starter.stack <= 0:
                raise GameError("请先准备再开始手牌。")
            runtime.start_hand()
            await self._run_bot_turns_locked(runtime)
        await self.connections.broadcast_state(runtime)
        return runtime

    async def submit_action(self, room: Room, user: User, action_type: str, amount: int = 0) -> RoomRuntime:
        runtime = self.room_manager.get_or_create(room)
        async with runtime.lock:
            runtime.submit_action(user.id, action_type, amount)
            await self._run_bot_turns_locked(runtime)
        await self.connections.broadcast_state(runtime)
        return runtime

    async def add_bot(
        self,
        room: Room,
        owner: User,
        seat_index: int,
        strategy: str,
        variant: str | None = None,
    ) -> RoomRuntime:
        if room.creator_id != owner.id:
            raise GameError("只有房主可以添加机器人。")
        try:
            strategy_name, variant_name = normalize_bot_selection(strategy, variant)
        except ValueError as exc:
            raise GameError(str(exc)) from exc

        runtime = self.room_manager.get_or_create(room)
        async with runtime.lock:
            if runtime.phase != WAITING:
                raise GameError("只能在两手牌之间添加机器人。")
            if seat_index < 0 or seat_index >= room.seat_count:
                raise GameError("座位无效。")
            if seat_index in runtime.players:
                raise GameError("该座位已被占用。")

            username = choose_bot_username({player.username for player in runtime.players.values()})
            bot = runtime.add_bot(username, seat_index, strategy_name, variant_name)
            runtime.set_ready(bot.user_id, True)
            if self._can_auto_start(runtime):
                runtime.start_hand()
            await self._run_bot_turns_locked(runtime)
        await self.connections.broadcast_state(runtime)
        return runtime

    async def remove_bot(self, room: Room, owner: User, seat_index: int) -> RoomRuntime:
        if room.creator_id != owner.id:
            raise GameError("只有房主可以删除机器人。")

        runtime = self.room_manager.get_or_create(room)
        async with runtime.lock:
            if runtime.phase != WAITING:
                raise GameError("只能在两手牌之间删除机器人。")
            player = runtime.players.get(seat_index)
            if player is None or player.player_type != "bot":
                raise GameError("该座位不是机器人。")
            runtime.unseat_player(seat_index)
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

    async def _run_bot_turns_locked(self, runtime: RoomRuntime) -> None:
        for _action_count in range(BOT_ACTION_LIMIT):
            self._ready_waiting_bots(runtime)
            if runtime.phase == WAITING:
                if self._can_auto_start(runtime):
                    runtime.start_hand()
                    continue
                return

            current_seat = runtime.current_turn_seat
            if current_seat is None:
                return
            player = runtime.players.get(current_seat)
            if player is None or player.player_type != "bot":
                return

            try:
                strategy = create_bot_strategy(player.bot_strategy or "check_fold", player.bot_variant)
            except ValueError as exc:
                raise GameError(str(exc)) from exc
            observation = runtime.bot_observation_for_user(player.user_id)
            await self.connections.broadcast_state(runtime)
            action = await strategy.act(observation, observation.legal_actions)
            runtime.submit_action(player.user_id, action.action_type, action.amount)
        raise GameError("机器人连续行动次数过多，请检查牌局状态。")

    def _ready_waiting_bots(self, runtime: RoomRuntime) -> None:
        if runtime.phase != WAITING:
            return
        for player in runtime.players.values():
            if player.player_type == "bot" and player.stack > 0 and not player.ready:
                runtime.set_ready(player.user_id, True)

    def _can_auto_start(self, runtime: RoomRuntime) -> bool:
        return runtime.can_start_hand() and any(
            player.player_type == "human" and player.ready and player.stack > 0
            for player in runtime.players.values()
        )


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
