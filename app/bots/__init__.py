"""Bot extension points."""

from app.bots.monte_carlo import MonteCarloBot, MonteCarloBotConfig
from app.bots.strategies import (
    BOT_NAME_POOL,
    BOT_STRATEGIES,
    BOT_STRATEGY_DEFINITIONS,
    BotStrategy,
    BotStrategyDefinition,
    BotVariantDefinition,
    CheckFoldBot,
    choose_bot_username,
    create_bot_strategy,
    list_bot_strategy_options,
    list_bot_strategies,
    normalize_bot_selection,
)

__all__ = [
    "BOT_NAME_POOL",
    "BOT_STRATEGIES",
    "BOT_STRATEGY_DEFINITIONS",
    "BotStrategy",
    "BotStrategyDefinition",
    "BotVariantDefinition",
    "CheckFoldBot",
    "MonteCarloBot",
    "MonteCarloBotConfig",
    "choose_bot_username",
    "create_bot_strategy",
    "list_bot_strategy_options",
    "list_bot_strategies",
    "normalize_bot_selection",
]

