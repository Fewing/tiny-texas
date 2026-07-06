import pytest

from app.db.models import Room, User
from app.game.runtime import GameError
from app.game.service import GameService
from app.realtime.manager import ConnectionManager
from app.rooms.manager import RoomManager


def make_room() -> Room:
    return Room(
        id=1,
        code="ABC123",
        name="Test",
        creator_id=1,
        seat_count=6,
        small_blind=5,
        big_blind=10,
        buy_in=1000,
    )


class EmptyRoomPlayerDb:
    def execute(self, *_args, **_kwargs):
        return self

    def scalars(self):
        return []


class RecordingConnectionManager(ConnectionManager):
    def __init__(self) -> None:
        super().__init__()
        self.snapshots: list[dict] = []

    async def broadcast_state(self, runtime):
        self.snapshots.append(
            {
                "current_turn_seat": runtime.current_turn_seat,
                "last_action": runtime.actions[-1].to_public() if runtime.actions else None,
            }
        )
        await super().broadcast_state(runtime)


@pytest.mark.asyncio
async def test_last_ready_player_starts_hand_automatically():
    room = make_room()
    service = GameService(RoomManager(), ConnectionManager())
    runtime = service.room_manager.get_or_create(room)
    runtime.seat_player(1, "alice", 0)
    runtime.seat_player(2, "bob", 1)

    await service.set_ready(room, User(id=1, username="alice", password_hash="hash"), True)

    assert runtime.phase == "waiting"
    assert runtime.hand_number == 0

    await service.set_ready(room, User(id=2, username="bob", password_hash="hash"), True)

    assert runtime.phase == "preflop"
    assert runtime.hand_number == 1
    assert len(runtime.players[0].hole_cards) == 2
    assert len(runtime.players[1].hole_cards) == 2


@pytest.mark.asyncio
async def test_unready_seated_player_cannot_start_ready_players_hand():
    room = make_room()
    service = GameService(RoomManager(), ConnectionManager())
    runtime = service.room_manager.get_or_create(room)
    runtime.seat_player(1, "alice", 0)
    runtime.seat_player(2, "bob", 1)
    runtime.seat_player(3, "cara", 2)
    runtime.set_ready(2, True)
    runtime.set_ready(3, True)
    user = User(id=1, username="alice", password_hash="hash")

    with pytest.raises(GameError, match="准备"):
        await service.start_hand(room, user)

    assert runtime.phase == "waiting"
    assert runtime.players[0].hole_cards == []


@pytest.mark.asyncio
async def test_owner_can_add_and_remove_memory_bot():
    room = make_room()
    owner = User(id=1, username="alice", password_hash="hash")
    service = GameService(RoomManager(), ConnectionManager())
    runtime = service.room_manager.get_or_create(room)
    runtime.seat_player(owner.id, owner.username, 0)

    await service.add_bot(room, owner, 1, "simple_monte_carlo", "tight")

    bot = runtime.players[1]
    assert bot.user_id < 0
    assert bot.username.endswith("BOT")
    assert bot.player_type == "bot"
    assert bot.bot_strategy == "simple_monte_carlo"
    assert bot.bot_variant == "tight"
    assert bot.ready is True

    await service.remove_bot(room, owner, 1)

    assert 1 not in runtime.players


def test_db_sync_preserves_memory_bots():
    room = make_room()
    manager = RoomManager()
    runtime = manager.get_or_create(room)
    runtime.add_bot("河牌魔术师BOT", 1, "check_fold", "default")

    manager.sync_from_db(EmptyRoomPlayerDb(), room)

    assert runtime.players[1].player_type == "bot"


@pytest.mark.asyncio
async def test_non_owner_cannot_add_or_remove_bot():
    room = make_room()
    service = GameService(RoomManager(), ConnectionManager())
    owner = User(id=1, username="alice", password_hash="hash")
    intruder = User(id=2, username="bob", password_hash="hash")

    with pytest.raises(GameError, match="房主"):
        await service.add_bot(room, intruder, 1, "check_fold", "default")

    await service.add_bot(room, owner, 1, "check_fold", "default")

    with pytest.raises(GameError, match="房主"):
        await service.remove_bot(room, intruder, 1)


@pytest.mark.asyncio
async def test_check_fold_bot_acts_after_human_action():
    room = make_room()
    user = User(id=1, username="alice", password_hash="hash")
    service = GameService(RoomManager(), ConnectionManager())
    runtime = service.room_manager.get_or_create(room)
    runtime.seat_player(user.id, user.username, 0)
    await service.add_bot(room, user, 1, "check_fold", "default")

    await service.set_ready(room, user, True)
    await service.submit_action(room, user, "call")

    bot = runtime.players[1]
    bot_actions = [action for action in runtime.actions if action.user_id == bot.user_id]

    assert bot_actions
    assert bot_actions[-1].action_type == "check"
    assert runtime.current_turn_seat == 0


@pytest.mark.asyncio
async def test_bot_turn_is_broadcast_before_bot_action():
    room = make_room()
    user = User(id=1, username="alice", password_hash="hash")
    connections = RecordingConnectionManager()
    service = GameService(RoomManager(), connections)
    runtime = service.room_manager.get_or_create(room)
    runtime.seat_player(user.id, user.username, 0)
    await service.add_bot(room, user, 1, "check_fold", "default")
    await service.set_ready(room, user, True)

    connections.snapshots.clear()
    await service.submit_action(room, user, "call")

    assert any(
        snapshot["current_turn_seat"] == 1
        and snapshot["last_action"]
        and snapshot["last_action"]["user_id"] == user.id
        and snapshot["last_action"]["action_type"] == "call"
        for snapshot in connections.snapshots
    )
