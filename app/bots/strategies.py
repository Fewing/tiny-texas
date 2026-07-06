from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from app.bots.evaluation import PREFLOP_SCORES, preflop_strength
from app.bots.monte_carlo import MonteCarloBotConfig, SimpleMonteCarloBot
from app.game.models import BotObservation, PlayerAction


class BotStrategy(Protocol):
    async def act(self, observation: BotObservation, legal_actions: list[dict]) -> PlayerAction:
        """Choose one legal action for a bot-controlled seat."""


class CheckFoldBot:
    async def act(self, observation: BotObservation, legal_actions: list[dict]) -> PlayerAction:
        legal_types = {action["type"] for action in legal_actions}
        if "check" in legal_types:
            return PlayerAction("check")
        return PlayerAction("fold")


@dataclass(frozen=True)
class BotVariantDefinition:
    label: str
    description: str
    factory: Callable[[], BotStrategy]


@dataclass(frozen=True)
class BotStrategyDefinition:
    label: str
    description: str
    default_variant: str
    variants: dict[str, BotVariantDefinition]


BOT_NAME_POOL = (
    "河牌魔术师",
    "黏黏怪",
    "口袋星人",
    "翻牌旅人",
    "转牌船长",
    "筹码炼金师",
    "小盲诗人",
    "大盲铁匠",
    "慢打大师",
    "跟注小子",
    "加注骑士",
    "全下阿福",
    "暗三条猎手",
    "顺子侦探",
    "同花画家",
    "葫芦店长",
    "边池会计",
    "按钮位队长",
    "听牌舞者",
    "顶对教授",
    "踢脚国王",
    "底池管家",
    "河边渔夫",
    "幸运茶杯",
    "沉默枪手",
    "霓虹跟注侠",
    "口袋火箭",
    "彩虹牌桌",
    "筹码雨人",
    "松凶小王子",
    "紧凶老干部",
    "读牌猫头鹰",
    "摊牌导演",
    "泡泡猎人",
    "边注厨师",
    "月光发牌员",
)


BOT_STRATEGY_DEFINITIONS: dict[str, BotStrategyDefinition] = {
    "check_fold": BotStrategyDefinition(
        label="Check/Fold",
        description="只在可以过牌时过牌，其他情况弃牌。",
        default_variant="default",
        variants={
            "default": BotVariantDefinition(
                label="默认",
                description="最保守的兜底策略。",
                factory=CheckFoldBot,
            ),
        },
    ),
    "simple_monte_carlo": BotStrategyDefinition(
        label="轻量 Monte Carlo",
        description="翻前规则表，翻后小样本胜率估算。",
        default_variant="balanced",
        variants={
            "tight": BotVariantDefinition(
                label="保守",
                description="少诈唬，只用较强胜率下注和加注。",
                factory=lambda: SimpleMonteCarloBot(
                    MonteCarloBotConfig(
                        value_bet_threshold=0.72,
                        value_raise_threshold=0.84,
                        bluff_frequency=0.03,
                    )
                ),
            ),
            "balanced": BotVariantDefinition(
                label="均衡",
                description="默认紧凶风格，兼顾稳定和主动性。",
                factory=lambda: SimpleMonteCarloBot(MonteCarloBotConfig()),
            ),
            "aggressive": BotVariantDefinition(
                label="激进",
                description="更频繁下注和诈唬，抽样稍少以控制成本。",
                factory=lambda: SimpleMonteCarloBot(
                    MonteCarloBotConfig(
                        value_bet_threshold=0.58,
                        value_raise_threshold=0.70,
                        bluff_frequency=0.12,
                    )
                ),
            ),
        },
    ),
}

BOT_STRATEGIES: dict[str, Callable[[], BotStrategy]] = {
    name: definition.variants[definition.default_variant].factory
    for name, definition in BOT_STRATEGY_DEFINITIONS.items()
}


def create_bot_strategy(name: str = "simple_monte_carlo", variant: str | None = None) -> BotStrategy:
    strategy_name, variant_name = normalize_bot_selection(name, variant)
    return BOT_STRATEGY_DEFINITIONS[strategy_name].variants[variant_name].factory()


def normalize_bot_selection(name: str = "simple_monte_carlo", variant: str | None = None) -> tuple[str, str]:
    try:
        definition = BOT_STRATEGY_DEFINITIONS[name]
    except KeyError as exc:
        known = ", ".join(sorted(BOT_STRATEGY_DEFINITIONS))
        raise ValueError(f"Unknown bot strategy '{name}'. Known strategies: {known}") from exc
    variant_name = variant or definition.default_variant
    if variant_name not in definition.variants:
        known = ", ".join(sorted(definition.variants))
        raise ValueError(f"Unknown bot variant '{variant_name}' for '{name}'. Known variants: {known}")
    return name, variant_name


def list_bot_strategies() -> list[str]:
    return sorted(BOT_STRATEGY_DEFINITIONS)


def list_bot_strategy_options() -> list[dict]:
    return [
        {
            "name": name,
            "label": definition.label,
            "description": definition.description,
            "default_variant": definition.default_variant,
            "variants": [
                {
                    "name": variant_name,
                    "label": variant.label,
                    "description": variant.description,
                }
                for variant_name, variant in definition.variants.items()
            ],
        }
        for name, definition in BOT_STRATEGY_DEFINITIONS.items()
    ]


def choose_bot_username(existing_usernames: set[str]) -> str:
    for _attempt in range(200):
        base_name = secrets.choice(BOT_NAME_POOL)
        candidate = f"{base_name}BOT"
        if candidate not in existing_usernames:
            return candidate
        suffix = secrets.choice("23456789ABCDEFGHJKMNPQRSTUVWXYZ")
        candidate = f"{base_name}{suffix}BOT"
        if len(candidate) <= 32 and candidate not in existing_usernames:
            return candidate
    return f"牌桌来客{secrets.token_hex(3).upper()}BOT"


__all__ = [
    "BOT_NAME_POOL",
    "BOT_STRATEGIES",
    "BOT_STRATEGY_DEFINITIONS",
    "BotStrategyDefinition",
    "BotVariantDefinition",
    "BotStrategy",
    "CheckFoldBot",
    "MonteCarloBotConfig",
    "PREFLOP_SCORES",
    "SimpleMonteCarloBot",
    "choose_bot_username",
    "create_bot_strategy",
    "list_bot_strategy_options",
    "list_bot_strategies",
    "normalize_bot_selection",
    "preflop_strength",
]

