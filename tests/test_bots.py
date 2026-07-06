import random

import pytest

from app.bots import (
    MonteCarloBotConfig,
    SimpleMonteCarloBot,
    choose_bot_username,
    create_bot_strategy,
    list_bot_strategy_options,
    list_bot_strategies,
)
from app.game.models import BotObservation


def make_observation(
    hole_cards: list[str],
    *,
    community_cards: list[str] | None = None,
    pot: int = 100,
    stack: int = 1000,
    legal_actions: list[dict] | None = None,
    opponent_count: int = 1,
) -> BotObservation:
    return BotObservation(
        room_code="ABC123",
        hand_number=1,
        seat_index=0,
        hole_cards=hole_cards,
        community_cards=community_cards or [],
        pot=pot,
        stack=stack,
        current_bet=0,
        legal_actions=legal_actions or [],
        action_history=[],
        opponent_count=opponent_count,
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
    bot = SimpleMonteCarloBot(MonteCarloBotConfig(action_delay_seconds=0), rng=random.Random(1))

    action = await bot.act(observation, legal_actions)

    assert action.action_type == "raise"
    assert 30 <= action.amount <= 1000


@pytest.mark.asyncio
async def test_monte_carlo_bot_folds_weak_preflop_hand_to_large_call():
    legal_actions = [
        {"type": "fold", "amount": 0},
        {"type": "call", "amount": 200, "to_call": 200},
        {"type": "all_in", "amount": 1000},
    ]
    observation = make_observation(["7c", "2d"], pot=50, legal_actions=legal_actions)
    bot = SimpleMonteCarloBot(MonteCarloBotConfig(action_delay_seconds=0), rng=random.Random(2))

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
    bot = SimpleMonteCarloBot(MonteCarloBotConfig(equity_samples=64, action_delay_seconds=0), rng=random.Random(3))

    assert bot.estimate_equity(observation) > 0.8

    action = await bot.act(observation, legal_actions)

    assert action.action_type == "bet"
    assert 10 <= action.amount <= 1000


def test_bot_strategy_registry_exposes_builtin_strategies():
    strategies = list_bot_strategies()

    assert "check_fold" in strategies
    assert "simple_monte_carlo" in strategies
    assert isinstance(create_bot_strategy(), SimpleMonteCarloBot)
    assert isinstance(create_bot_strategy("simple_monte_carlo", "aggressive"), SimpleMonteCarloBot)

    options = list_bot_strategy_options()
    monte_carlo = next(option for option in options if option["name"] == "simple_monte_carlo")

    assert monte_carlo["default_variant"] == "balanced"
    assert {variant["name"] for variant in monte_carlo["variants"]} == {"tight", "balanced", "aggressive"}


def test_choose_bot_username_uses_chinese_pool_and_bot_suffix():
    username = choose_bot_username(set())

    assert username.endswith("BOT")
    assert len(username) <= 32


def test_legacy_strategies_module_reexports_public_bot_api():
    from app.bots.strategies import SimpleMonteCarloBot as LegacyMonteCarloBot

    assert LegacyMonteCarloBot is SimpleMonteCarloBot
