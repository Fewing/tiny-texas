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
