from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass

from app.bots.evaluation import estimate_monte_carlo_equity, preflop_strength
from app.game.models import BotObservation, PlayerAction


@dataclass(frozen=True)
class MonteCarloBotConfig:
    # Random completions sampled per postflop decision; higher is stronger but slower.
    equity_samples: int = 256
    # Opponent cap used by equity simulation to keep CPU cost predictable.
    max_opponents: int = 8
    # Minimum estimated equity for betting when no call is required.
    value_bet_threshold: float = 0.67
    # Minimum estimated equity for raising over an existing bet.
    value_raise_threshold: float = 0.78
    # Chance to make a small bet with weak postflop equity when checking is available.
    bluff_frequency: float = 0.06
    # Delay before returning an action so Monte Carlo bots feel less instant.
    action_delay_seconds: float = 2.0


class SimpleMonteCarloBot:
    """Tight-aggressive bot with preflop rules and small postflop equity samples."""

    def __init__(self, config: MonteCarloBotConfig | None = None, rng: random.Random | None = None) -> None:
        self.config = config or MonteCarloBotConfig()
        self.rng = rng or random.Random()

    async def act(self, observation: BotObservation, legal_actions: list[dict]) -> PlayerAction:
        actions = legal_actions or observation.legal_actions
        if not actions:
            raise ValueError("Bot cannot act without legal actions.")

        if self.config.action_delay_seconds > 0:
            await asyncio.sleep(self.config.action_delay_seconds)

        if not observation.community_cards:
            strength = preflop_strength(observation.hole_cards)
            return self._act_from_strength(strength, observation, actions, is_equity=False)

        equity = self.estimate_equity(observation)
        return self._act_from_strength(equity, observation, actions, is_equity=True)

    def estimate_equity(self, observation: BotObservation) -> float:
        return estimate_monte_carlo_equity(
            observation.hole_cards,
            observation.community_cards,
            opponent_count=observation.opponent_count,
            samples=self.config.equity_samples,
            max_opponents=self.config.max_opponents,
            rng=self.rng,
        )

    def _act_from_strength(
        self,
        strength: float,
        observation: BotObservation,
        legal_actions: list[dict],
        *,
        is_equity: bool,
    ) -> PlayerAction:
        call_action = _find_action(legal_actions, "call")
        check_action = _find_action(legal_actions, "check")
        raise_action = _find_action(legal_actions, "raise")
        bet_action = _find_action(legal_actions, "bet")
        all_in_action = _find_action(legal_actions, "all_in")

        if call_action is not None:
            call_amount = int(call_action.get("amount", 0))
            pot_odds = call_amount / max(1, observation.pot + call_amount)
            if raise_action is not None and strength >= self._raise_threshold(is_equity):
                return _sized_action(raise_action, observation, fraction=0.7)
            if all_in_action is not None and strength >= 0.93 and call_amount >= observation.stack:
                return PlayerAction("all_in", int(all_in_action.get("amount", 0)))
            if strength >= max(0.36 if is_equity else 0.44, pot_odds + (0.08 if is_equity else 0.15)):
                return PlayerAction("call", call_amount)
            return _fallback_passive(legal_actions)

        if check_action is not None:
            pressure_action = bet_action or raise_action
            if pressure_action is not None and strength >= self._bet_threshold(is_equity):
                return _sized_action(pressure_action, observation, fraction=0.55)
            if bet_action is not None and is_equity and strength < 0.32 and self.rng.random() < self.config.bluff_frequency:
                return _sized_action(bet_action, observation, fraction=0.35)
            return PlayerAction("check")

        if bet_action is not None and strength >= self._bet_threshold(is_equity):
            return _sized_action(bet_action, observation, fraction=0.55)
        if all_in_action is not None and strength >= 0.94:
            return PlayerAction("all_in", int(all_in_action.get("amount", 0)))
        return _fallback_passive(legal_actions)

    def _bet_threshold(self, is_equity: bool) -> float:
        return self.config.value_bet_threshold if is_equity else 0.78

    def _raise_threshold(self, is_equity: bool) -> float:
        return self.config.value_raise_threshold if is_equity else 0.86


def _find_action(legal_actions: list[dict], action_type: str) -> dict | None:
    return next((action for action in legal_actions if action.get("type") == action_type), None)


def _sized_action(action: dict, observation: BotObservation, *, fraction: float) -> PlayerAction:
    minimum = int(action.get("min", action.get("amount", 0)))
    maximum = int(action.get("max", action.get("amount", minimum)))
    if maximum <= minimum:
        return PlayerAction(str(action["type"]), minimum)
    pot_target = int(observation.pot * fraction)
    target = max(minimum, min(maximum, pot_target))
    return PlayerAction(str(action["type"]), target)


def _fallback_passive(legal_actions: list[dict]) -> PlayerAction:
    for action_type in ("check", "fold", "call", "all_in"):
        action = _find_action(legal_actions, action_type)
        if action is not None:
            return PlayerAction(action_type, int(action.get("amount", 0)))
    action = legal_actions[0]
    return PlayerAction(str(action["type"]), int(action.get("min", action.get("amount", 0))))
