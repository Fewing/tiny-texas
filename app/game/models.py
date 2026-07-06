from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlayerAction:
    action_type: str
    amount: int = 0


@dataclass(frozen=True)
class BotObservation:
    room_code: str
    hand_number: int
    seat_index: int
    hole_cards: list[str]
    community_cards: list[str]
    pot: int
    stack: int
    current_bet: int
    legal_actions: list[dict]
    action_history: list[dict]
    opponent_count: int = 1

