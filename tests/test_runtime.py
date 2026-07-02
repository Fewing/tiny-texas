from app.game.runtime import RoomConfig, RoomRuntime


def make_runtime() -> RoomRuntime:
    return RoomRuntime(
        RoomConfig(
            room_id=1,
            code="ABC123",
            name="Test",
            seat_count=6,
            small_blind=5,
            big_blind=10,
            buy_in=1000,
        )
    )


def seat_two_players(runtime: RoomRuntime) -> None:
    runtime.seat_player(1, "alice", 0)
    runtime.seat_player(2, "bob", 1)
    runtime.set_ready(1, True)
    runtime.set_ready(2, True)


def test_public_state_hides_other_players_hole_cards():
    runtime = make_runtime()
    seat_two_players(runtime)

    runtime.start_hand()

    alice_state = runtime.public_state(1)
    alice_seat = alice_state["players"][0]
    bob_seat = alice_state["players"][1]

    assert len(alice_seat["hole_cards"]) == 2
    assert bob_seat["hole_cards"] == ["XX", "XX"]


def test_fold_awards_pot_and_finishes_hand():
    runtime = make_runtime()
    seat_two_players(runtime)

    runtime.start_hand()
    current_user_id = runtime.players[runtime.current_turn_seat].user_id
    runtime.submit_action(current_user_id, "fold")

    assert runtime.phase == "waiting"
    assert runtime.last_result is not None
    assert runtime.last_result.reason == "fold"
    assert runtime.last_result.pot == 15
    assert runtime.last_result.showdown_players == []


def test_rebuy_adds_room_scoped_player_marker():
    runtime = make_runtime()
    runtime.seat_player(1, "alice", 0)
    runtime.players[0].stack = 0

    runtime.set_ready(1, True)

    assert runtime.players[0].stack == 1000
    assert runtime.rebuy_counts[1] == 1
    assert runtime.public_state(1)["players"][0]["rebuy_count"] == 1

    other_room = make_runtime()
    other_room.seat_player(1, "alice", 0)

    assert other_room.public_state(1)["players"][0]["rebuy_count"] == 0


def test_stack_survives_stand_and_reseat():
    runtime = make_runtime()
    runtime.seat_player(1, "alice", 0)
    runtime.players[0].stack = 725

    runtime.stand_player(1)
    runtime.seat_player(1, "alice", 2)

    assert 0 not in runtime.players
    assert runtime.players[2].stack == 725
    assert runtime.public_state(1)["players"][2]["stack"] == 725


def test_stack_survives_direct_seat_change():
    runtime = make_runtime()
    runtime.seat_player(1, "alice", 0)
    runtime.players[0].stack = 640

    runtime.seat_player(1, "alice", 3)

    assert 0 not in runtime.players
    assert runtime.players[3].stack == 640


def test_unready_viewer_cannot_start_ready_players_hand():
    runtime = make_runtime()
    runtime.seat_player(1, "alice", 0)
    runtime.seat_player(2, "bob", 1)
    runtime.seat_player(3, "cara", 2)
    runtime.set_ready(2, True)
    runtime.set_ready(3, True)

    assert runtime.can_start_hand()
    assert runtime.public_state(1)["can_start"] is False
    assert runtime.public_state(2)["can_start"] is True


def test_showdown_side_pot_awards_are_settled():
    runtime = make_runtime()
    runtime.seat_player(1, "alice", 0)
    runtime.seat_player(2, "bob", 1)
    runtime.seat_player(3, "cara", 2)
    for user_id in (1, 2, 3):
        runtime.set_ready(user_id, True)
    runtime.start_hand()

    runtime.phase = "river"
    runtime.community_cards = ["2c", "3d", "4h", "9s", "Td"]
    runtime.players[0].hole_cards = ["As", "Ah"]
    runtime.players[1].hole_cards = ["Ks", "Kh"]
    runtime.players[2].hole_cards = ["Qs", "Qh"]
    runtime.players[0].total_bet = 100
    runtime.players[1].total_bet = 50
    runtime.players[2].total_bet = 100
    runtime.players[0].stack = 900
    runtime.players[1].stack = 950
    runtime.players[2].stack = 900

    result = runtime._finish_showdown()

    assert result.pot == 250
    assert runtime.players[0].stack == 1150
    assert runtime.players[1].stack == 950
    assert runtime.players[2].stack == 900
    assert result.showdown_players == [
        {
            "user_id": 1,
            "username": "alice",
            "seat_index": 0,
            "hole_cards": ["As", "Ah"],
            "hand_rank": "一对",
        },
        {
            "user_id": 2,
            "username": "bob",
            "seat_index": 1,
            "hole_cards": ["Ks", "Kh"],
            "hand_rank": "一对",
        },
        {
            "user_id": 3,
            "username": "cara",
            "seat_index": 2,
            "hole_cards": ["Qs", "Qh"],
            "hand_rank": "一对",
        },
    ]
    assert result.to_public()["showdown_players"] == result.showdown_players
