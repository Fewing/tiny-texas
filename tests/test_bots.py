import random

import pytest

from app.bots import (
    MonteCarloBot,
    MonteCarloBotConfig,
    choose_bot_username,
    create_bot_strategy,
    list_bot_strategy_options,
    list_bot_strategies,
)
from app.game.models import BotObservation


def fast_config(**overrides) -> MonteCarloBotConfig:
    values = {
        "decision_time_seconds": 0,
        "minimum_action_seconds": 0,
        "equity_samples": 128,
        "max_equity_samples": 128,
    }
    values.update(overrides)
    return MonteCarloBotConfig(**values)


def make_observation(
    hole_cards: list[str],
    *,
    community_cards: list[str] | None = None,
    pot: int = 100,
    stack: int = 1000,
    legal_actions: list[dict] | None = None,
    opponent_count: int = 1,
    action_history: list[dict] | None = None,
    position: str = "middle",
    players_to_act: int = 1,
) -> BotObservation:
    board = community_cards or []
    phase = {0: "preflop", 3: "flop", 4: "turn", 5: "river"}.get(len(board), "preflop")
    return BotObservation(
        room_code="ABC123",
        hand_number=1,
        phase=phase,
        seat_index=0,
        hole_cards=hole_cards,
        community_cards=board,
        pot=pot,
        stack=stack,
        current_bet=0,
        legal_actions=legal_actions or [],
        action_history=action_history or [],
        opponent_count=opponent_count,
        active_seat_count=opponent_count + 1,
        players_to_act=players_to_act,
        position=position,
    )


@pytest.mark.asyncio
async def test_monte_carlo_bot_raises_premium_preflop_hand():
    legal_actions = [
        {"type": "fold", "amount": 0},
        {"type": "call", "amount": 10, "to_call": 10},
        {"type": "raise", "min": 30, "max": 1000},
        {"type": "all_in", "amount": 1000},
    ]
    observation = make_observation(["As", "Ah"], pot=15, legal_actions=legal_actions)
    bot = MonteCarloBot(fast_config(), rng=random.Random(1))

    action = await bot.act(observation, legal_actions)

    assert action.action_type == "raise"
    assert action.amount >= 30


@pytest.mark.asyncio
async def test_monte_carlo_bot_folds_weak_preflop_hand_to_large_call():
    legal_actions = [
        {"type": "fold", "amount": 0},
        {"type": "call", "amount": 200, "to_call": 200},
        {"type": "all_in", "amount": 1000},
    ]
    observation = make_observation(["7c", "2d"], pot=50, legal_actions=legal_actions)
    bot = MonteCarloBot(fast_config(), rng=random.Random(2))

    action = await bot.act(observation, legal_actions)

    assert action.action_type == "fold"


@pytest.mark.asyncio
async def test_monte_carlo_bot_bets_strong_postflop_equity():
    legal_actions = [
        {"type": "check", "amount": 0},
        {"type": "bet", "min": 10, "max": 1000},
        {"type": "all_in", "amount": 1000},
    ]
    observation = make_observation(
        ["As", "Ks"],
        community_cards=["Qs", "Js", "2s"],
        pot=120,
        legal_actions=legal_actions,
    )
    bot = MonteCarloBot(fast_config(), rng=random.Random(3))

    assert bot.estimate_equity(observation) > 0.8

    action = await bot.act(observation, legal_actions)

    assert action.action_type == "bet"
    assert 10 <= action.amount <= 1000


@pytest.mark.asyncio
async def test_monte_carlo_bot_uses_larger_value_size_for_monster_hand():
    legal_actions = [
        {"type": "check", "amount": 0},
        {"type": "bet", "min": 10, "max": 1000},
        {"type": "all_in", "amount": 1000},
    ]
    observation = make_observation(
        ["As", "Ah"],
        community_cards=["Ad", "Kd", "Kc"],
        pot=180,
        legal_actions=legal_actions,
    )
    bot = MonteCarloBot(fast_config(), rng=random.Random(4))

    action = await bot.act(observation, legal_actions)

    assert action.action_type == "bet"
    assert action.amount >= 175


def test_bot_strategy_registry_exposes_builtin_strategies():
    strategies = list_bot_strategies()

    assert "check_fold" in strategies
    assert "monte_carlo" in strategies
    assert "simple_monte_carlo" not in strategies
    assert isinstance(create_bot_strategy(), MonteCarloBot)
    assert isinstance(create_bot_strategy("monte_carlo", "aggressive"), MonteCarloBot)

    options = list_bot_strategy_options()
    monte_carlo = next(option for option in options if option["name"] == "monte_carlo")

    assert monte_carlo["default_variant"] == "balanced"
    assert {variant["name"] for variant in monte_carlo["variants"]} == {"tight", "balanced", "aggressive"}


def test_choose_bot_username_uses_chinese_pool_and_bot_suffix():
    username = choose_bot_username(set())

    assert username.endswith("BOT")
    assert len(username) <= 32
