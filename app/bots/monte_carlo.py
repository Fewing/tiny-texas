from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass

from app.bots.evaluation import preflop_strength
from app.game.cards import new_deck
from app.game.evaluator import evaluate
from app.game.models import BotObservation, PlayerAction


@dataclass(frozen=True)
class MonteCarloBotConfig:
    # Minimum samples to run when estimating postflop equity.
    equity_samples: int = 512
    # Hard sample cap for one decision, even when time budget remains.
    max_equity_samples: int = 3000
    # Opponent cap used by equity simulation to keep CPU cost predictable.
    max_opponents: int = 8
    # Total decision budget. Postflop uses it for sampling; preflop waits out the rest.
    decision_time_seconds: float = 0.5
    # Minimum visible thinking time for one bot action.
    minimum_action_seconds: float = 0.5
    # Minimum estimated equity for value betting when no call is required.
    value_bet_threshold: float = 0.62
    # Minimum estimated equity for value raising over an existing bet.
    value_raise_threshold: float = 0.74
    # Chance to make a small bluff when equity is too low for value.
    bluff_frequency: float = 0.06
    # Low-SPR all-in threshold for strong value hands.
    all_in_spr_threshold: float = 2.2
    # Sizing and thin-value multiplier. Below 1 is tighter, above 1 is more forceful.
    aggression: float = 1.0


class MonteCarloBot:
    """Range-aware Monte Carlo bot with simple EV-based action selection."""

    def __init__(self, config: MonteCarloBotConfig | None = None, rng: random.Random | None = None) -> None:
        self.config = config or MonteCarloBotConfig()
        self.rng = rng or random.Random()

    async def act(self, observation: BotObservation, legal_actions: list[dict]) -> PlayerAction:
        actions = legal_actions or observation.legal_actions
        if not actions:
            raise ValueError("Bot cannot act without legal actions.")

        started_at = time.monotonic()
        if observation.community_cards:
            equity = self.estimate_equity(observation, started_at=started_at)
            action = self._act_postflop(equity, observation, actions)
        else:
            action = self._act_preflop(observation, actions)

        await self._wait_remaining(started_at)
        return action

    def estimate_equity(self, observation: BotObservation, *, started_at: float | None = None) -> float:
        deadline = None
        if started_at is not None and self.config.decision_time_seconds > 0:
            deadline = started_at + self.config.decision_time_seconds
        return self._estimate_equity_against_ranges(observation, deadline)

    def _act_preflop(self, observation: BotObservation, legal_actions: list[dict]) -> PlayerAction:
        strength = _clamp(
            preflop_strength(observation.hole_cards)
            + _position_adjustment(observation)
            - _multiway_penalty(observation)
            - _aggression_pressure(observation) * 0.45,
            0.0,
            1.0,
        )
        call_action = _find_action(legal_actions, "call")
        check_action = _find_action(legal_actions, "check")
        raise_action = _find_action(legal_actions, "raise")
        all_in_action = _find_action(legal_actions, "all_in")

        if call_action is not None:
            call_amount = int(call_action.get("amount", 0))
            pot_odds = call_amount / max(1, observation.pot + call_amount)
            raise_threshold = self._preflop_raise_threshold(observation)
            call_threshold = max(0.36, pot_odds + 0.10 + _multiway_penalty(observation))
            if raise_action is not None and strength >= raise_threshold:
                return _sized_action(
                    raise_action,
                    observation,
                    fraction=self._preflop_raise_fraction(strength, observation),
                )
            if all_in_action is not None and strength >= 0.96 and call_amount >= observation.stack:
                return PlayerAction("all_in", int(all_in_action.get("amount", 0)))
            if strength >= call_threshold:
                return PlayerAction("call", call_amount)
            return _fallback_passive(legal_actions)

        if check_action is not None:
            pressure_action = _find_action(legal_actions, "bet") or raise_action
            if pressure_action is not None and strength >= self._preflop_raise_threshold(observation) + 0.04:
                return _sized_action(pressure_action, observation, fraction=1.6)
            return PlayerAction("check")

        return _fallback_passive(legal_actions)

    def _act_postflop(
        self,
        equity: float,
        observation: BotObservation,
        legal_actions: list[dict],
    ) -> PlayerAction:
        passive_action, passive_ev = self._best_passive_action(equity, observation, legal_actions)
        best_action = passive_action
        best_ev = passive_ev
        made_category = _made_hand_category(observation)

        for action in legal_actions:
            action_type = str(action.get("type"))
            if action_type not in {"bet", "raise"}:
                continue
            if not self._should_apply_pressure(action_type, equity, made_category):
                continue
            for fraction in self._sizing_fractions(equity, made_category, observation):
                candidate = _sized_action(action, observation, fraction=fraction)
                candidate_ev = self._pressure_ev(candidate, equity, observation)
                if candidate_ev > best_ev:
                    best_action = candidate
                    best_ev = candidate_ev

        all_in_action = _find_action(legal_actions, "all_in")
        if all_in_action is not None and self._should_consider_all_in(equity, made_category, observation):
            candidate = PlayerAction("all_in", int(all_in_action.get("amount", 0)))
            candidate_ev = self._pressure_ev(candidate, equity, observation)
            if candidate_ev > best_ev:
                best_action = candidate
                best_ev = candidate_ev

        margin = max(2.0, observation.pot * (0.035 / max(0.7, self.config.aggression)))
        if best_action != passive_action and best_ev >= passive_ev + margin:
            return best_action
        return passive_action

    def _best_passive_action(
        self,
        equity: float,
        observation: BotObservation,
        legal_actions: list[dict],
    ) -> tuple[PlayerAction, float]:
        call_action = _find_action(legal_actions, "call")
        check_action = _find_action(legal_actions, "check")
        if check_action is not None:
            return PlayerAction("check"), equity * observation.pot
        if call_action is not None:
            call_amount = int(call_action.get("amount", 0))
            call_ev = equity * (observation.pot + call_amount) - call_amount
            pot_odds = call_amount / max(1, observation.pot + call_amount)
            required = pot_odds + 0.035 + _multiway_penalty(observation) * 0.55
            if call_ev >= 0 and equity >= required:
                return PlayerAction("call", call_amount), call_ev
            fold_action = _find_action(legal_actions, "fold")
            if fold_action is not None:
                return PlayerAction("fold"), 0.0
        return _fallback_passive(legal_actions), 0.0

    def _pressure_ev(self, action: PlayerAction, equity: float, observation: BotObservation) -> float:
        cost = _commit_cost(action, observation)
        if cost <= 0:
            return equity * observation.pot
        fold_equity = self._fold_equity(action, equity, observation)
        called_ev = equity * (observation.pot + cost) - (1.0 - equity) * cost
        return fold_equity * observation.pot + (1.0 - fold_equity) * called_ev

    def _fold_equity(self, action: PlayerAction, equity: float, observation: BotObservation) -> float:
        cost = _commit_cost(action, observation)
        pot_fraction = cost / max(1, observation.pot)
        pressure = 0.07 + max(0.0, pot_fraction - 0.45) * 0.12
        pressure += max(0.0, 0.48 - equity) * 0.18
        pressure += max(0.0, self.config.aggression - 1.0) * 0.04
        pressure -= _multiway_penalty(observation) * 0.8
        pressure -= _aggression_pressure(observation) * 0.35
        if equity >= 0.78:
            pressure *= 0.45
        return _clamp(pressure, 0.01, 0.42)

    def _should_apply_pressure(self, action_type: str, equity: float, made_category: int) -> bool:
        threshold = self.config.value_raise_threshold if action_type == "raise" else self.config.value_bet_threshold
        threshold -= max(0.0, self.config.aggression - 1.0) * 0.04
        if equity >= threshold:
            return True
        if made_category >= 3 and equity >= threshold - 0.08:
            return True
        return equity < 0.38 and self.rng.random() < self.config.bluff_frequency

    def _should_consider_all_in(self, equity: float, made_category: int, observation: BotObservation) -> bool:
        spr = observation.stack / max(1, observation.pot)
        if spr <= self.config.all_in_spr_threshold and equity >= 0.78:
            return True
        if observation.phase == "river" and equity >= 0.94 and made_category >= 5:
            return True
        return equity >= 0.97 and made_category >= 7

    def _sizing_fractions(self, equity: float, made_category: int, observation: BotObservation) -> list[float]:
        if made_category >= 6 or equity >= 0.90:
            fractions = [0.78, 1.0, 1.2]
        elif made_category >= 3 or equity >= 0.78:
            fractions = [0.58, 0.75, 0.95]
        elif equity >= 0.62:
            fractions = [0.45, 0.62]
        else:
            fractions = [0.38]
        if observation.phase == "river" and equity >= 0.80:
            fractions.append(1.15)
        multiplier = _clamp(self.config.aggression, 0.75, 1.35)
        return sorted({max(0.25, fraction * multiplier) for fraction in fractions})

    def _preflop_raise_threshold(self, observation: BotObservation) -> float:
        threshold = 0.82 + _multiway_penalty(observation) * 0.7 - _position_adjustment(observation)
        threshold -= max(0.0, self.config.aggression - 1.0) * 0.035
        return _clamp(threshold, 0.70, 0.92)

    def _preflop_raise_fraction(self, strength: float, observation: BotObservation) -> float:
        fraction = 1.35 + observation.opponent_count * 0.18
        if strength >= 0.92:
            fraction += 0.45
        if observation.position == "early":
            fraction += 0.12
        return fraction * _clamp(self.config.aggression, 0.85, 1.25)

    def _estimate_equity_against_ranges(self, observation: BotObservation, deadline: float | None) -> float:
        known_cards = list(observation.hole_cards) + list(observation.community_cards)
        remaining_cards = [card for card in new_deck() if card not in known_cards]
        opponent_count = max(1, min(self.config.max_opponents, observation.opponent_count))
        board_needed = 5 - len(observation.community_cards)
        cards_needed = board_needed + opponent_count * 2
        if len(observation.hole_cards) != 2 or board_needed < 0 or len(remaining_cards) < cards_needed:
            return 0.0

        min_samples = max(1, self.config.equity_samples)
        max_samples = max(min_samples, self.config.max_equity_samples)
        range_floor = self._opponent_range_floor(observation)
        equity = 0.0
        samples = 0

        while samples < max_samples:
            if samples >= min_samples and deadline is not None and time.monotonic() >= deadline:
                break

            deck = list(remaining_cards)
            self.rng.shuffle(deck)
            board = list(observation.community_cards)
            board.extend(deck[:board_needed])
            available = deck[board_needed:]
            opponent_values = []

            for _opponent in range(opponent_count):
                opponent_hole = _draw_ranged_hole(available, range_floor, self.rng)
                if len(opponent_hole) != 2:
                    break
                opponent_values.append(evaluate(opponent_hole + board))
            if len(opponent_values) != opponent_count:
                break

            hero_value = evaluate(list(observation.hole_cards) + board)
            best_opponent = max(opponent_values)
            if hero_value > best_opponent:
                equity += 1.0
            elif hero_value == best_opponent:
                tied_opponents = sum(1 for value in opponent_values if value == hero_value)
                equity += 1.0 / (tied_opponents + 1)
            samples += 1

        return equity / max(1, samples)

    def _opponent_range_floor(self, observation: BotObservation) -> float:
        floor = 0.10 + _aggression_pressure(observation)
        floor += min(0.10, max(0, observation.opponent_count - 1) * 0.025)
        if observation.position == "early":
            floor += 0.02
        return _clamp(floor, 0.08, 0.56)

    async def _wait_remaining(self, started_at: float) -> None:
        remaining = self.config.minimum_action_seconds - (time.monotonic() - started_at)
        if remaining > 0:
            await asyncio.sleep(remaining)


def _find_action(legal_actions: list[dict], action_type: str) -> dict | None:
    return next((action for action in legal_actions if action.get("type") == action_type), None)


def _fallback_passive(legal_actions: list[dict]) -> PlayerAction:
    for action_type in ("check", "fold", "call", "all_in"):
        action = _find_action(legal_actions, action_type)
        if action is not None:
            return PlayerAction(action_type, int(action.get("amount", 0)))
    action = legal_actions[0]
    return PlayerAction(str(action["type"]), int(action.get("min", action.get("amount", 0))))


def _sized_action(action: dict, observation: BotObservation, *, fraction: float) -> PlayerAction:
    action_type = str(action["type"])
    minimum = int(action.get("min", action.get("amount", 0)))
    maximum = int(action.get("max", action.get("amount", minimum)))
    if maximum <= minimum:
        return PlayerAction(action_type, minimum)
    raw_target = int(observation.pot * fraction) + max(0, observation.current_bet)
    target = _round_amount(max(minimum, min(maximum, raw_target)))
    return PlayerAction(action_type, max(minimum, min(maximum, target)))


def _commit_cost(action: PlayerAction, observation: BotObservation) -> int:
    if action.action_type == "all_in":
        return observation.stack
    if action.action_type == "call":
        return action.amount
    if action.action_type in {"bet", "raise"}:
        return max(0, action.amount - observation.current_bet)
    return 0


def _draw_ranged_hole(available: list[str], strength_floor: float, rng: random.Random) -> list[str]:
    if len(available) < 2:
        return []

    best_pair: list[str] | None = None
    best_strength = -1.0
    attempts = 14 + int(strength_floor * 30)
    for _attempt in range(attempts):
        first, second = rng.sample(range(len(available)), 2)
        pair = [available[first], available[second]]
        strength = preflop_strength(pair)
        if strength >= strength_floor:
            _remove_cards(available, pair)
            return pair
        if strength > best_strength:
            best_pair = pair
            best_strength = strength

    pair = best_pair or available[:2]
    _remove_cards(available, pair)
    return pair


def _remove_cards(cards: list[str], removed_cards: list[str]) -> None:
    for card in removed_cards:
        cards.remove(card)


def _made_hand_category(observation: BotObservation) -> int:
    cards = list(observation.hole_cards) + list(observation.community_cards)
    if len(cards) < 5:
        return 0
    return evaluate(cards).category


def _position_adjustment(observation: BotObservation) -> float:
    if observation.position == "heads_up":
        return 0.035
    if observation.position == "late":
        return 0.045
    if observation.position == "early":
        return -0.045
    if observation.players_to_act >= 3:
        return -0.025
    return 0.0


def _multiway_penalty(observation: BotObservation) -> float:
    return min(0.12, max(0, observation.opponent_count - 1) * 0.028)


def _aggression_pressure(observation: BotObservation) -> float:
    pressure = 0.0
    for action in observation.action_history:
        if action.get("hand_number") != observation.hand_number:
            continue
        if action.get("seat_index") == observation.seat_index:
            continue
        action_type = action.get("action_type")
        if action_type in {"bet", "raise", "all_in"}:
            pressure += 0.065
        elif action_type == "call":
            pressure += 0.022
    return min(0.24, pressure)


def _round_amount(amount: int) -> int:
    chip = 5
    return max(chip, int((amount + chip / 2) // chip * chip))


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
