from app.game.evaluator import evaluate


def test_straight_flush_beats_four_of_a_kind():
    straight_flush = evaluate(["As", "Ks", "Qs", "Js", "Ts", "2d", "3c"])
    quads = evaluate(["Ah", "Ad", "Ac", "As", "Kd", "2c", "3h"])

    assert straight_flush > quads
    assert straight_flush.name == "同花顺"


def test_wheel_straight_is_detected():
    value = evaluate(["As", "2d", "3h", "4c", "5s", "Kd", "Qh"])

    assert value.name == "顺子"
    assert value.kickers == (5,)
