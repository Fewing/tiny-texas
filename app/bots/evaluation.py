from __future__ import annotations

import random

from app.game.cards import new_deck
from app.game.evaluator import RANK_VALUE, evaluate


def preflop_strength(hole_cards: list[str]) -> float:
    if len(hole_cards) != 2:
        return 0.0

    key = starting_hand_key(hole_cards)
    if key in PREFLOP_SCORES:
        return PREFLOP_SCORES[key]

    ranks = sorted((RANK_VALUE[card[0]] for card in hole_cards), reverse=True)
    high, low = ranks
    suited = hole_cards[0][1] == hole_cards[1][1]
    gap = high - low - 1
    broadway_count = sum(1 for rank in ranks if rank >= RANK_VALUE["T"])
    score = 0.16 + ((high + low) - 4) / 24 * 0.34
    if high == RANK_VALUE["A"]:
        score += 0.08
    if suited:
        score += 0.06
    if broadway_count == 2:
        score += 0.08
    if gap == 0:
        score += 0.04
    elif gap == 1:
        score += 0.02
    elif gap >= 4:
        score -= 0.08
    if high == RANK_VALUE["A"] and suited and low <= RANK_VALUE["5"]:
        score += 0.04
    return max(0.05, min(0.74, score))


def starting_hand_key(hole_cards: list[str]) -> str:
    ranks = sorted((card[0] for card in hole_cards), key=RANK_VALUE.__getitem__, reverse=True)
    if ranks[0] == ranks[1]:
        return ranks[0] + ranks[1]
    suffix = "s" if hole_cards[0][1] == hole_cards[1][1] else "o"
    return "".join(ranks) + suffix


def estimate_monte_carlo_equity(
    hole_cards: list[str],
    community_cards: list[str],
    *,
    opponent_count: int,
    samples: int,
    max_opponents: int,
    rng: random.Random,
) -> float:
    known_cards = list(hole_cards) + list(community_cards)
    remaining_cards = [card for card in new_deck() if card not in known_cards]
    opponent_count = max(1, min(max_opponents, opponent_count))
    board_needed = 5 - len(community_cards)
    cards_needed = board_needed + opponent_count * 2
    if len(hole_cards) != 2 or board_needed < 0 or len(remaining_cards) < cards_needed:
        return 0.0

    equity = 0.0
    for _sample in range(max(1, samples)):
        deck = list(remaining_cards)
        rng.shuffle(deck)
        board = list(community_cards)
        board.extend(deck[:board_needed])
        offset = board_needed
        hero_value = evaluate(list(hole_cards) + board)
        opponent_values = []
        for opponent_index in range(opponent_count):
            start = offset + opponent_index * 2
            opponent_hole = deck[start : start + 2]
            opponent_values.append(evaluate(opponent_hole + board))
        best_opponent = max(opponent_values)
        if hero_value > best_opponent:
            equity += 1.0
        elif hero_value == best_opponent:
            tied_opponents = sum(1 for value in opponent_values if value == hero_value)
            equity += 1.0 / (tied_opponents + 1)
    return equity / max(1, samples)


PREFLOP_SCORES = {
    "AA": 0.97,
    "KK": 0.94,
    "QQ": 0.91,
    "JJ": 0.87,
    "TT": 0.82,
    "99": 0.76,
    "88": 0.70,
    "77": 0.65,
    "66": 0.60,
    "55": 0.56,
    "44": 0.52,
    "33": 0.49,
    "22": 0.46,
    "AKs": 0.88,
    "AKo": 0.84,
    "AQs": 0.81,
    "AQo": 0.75,
    "AJs": 0.73,
    "AJo": 0.66,
    "ATs": 0.70,
    "ATo": 0.61,
    "A9s": 0.58,
    "A8s": 0.56,
    "A7s": 0.54,
    "A6s": 0.53,
    "A5s": 0.57,
    "A4s": 0.55,
    "A3s": 0.53,
    "A2s": 0.51,
    "KQs": 0.77,
    "KQo": 0.69,
    "KJs": 0.70,
    "KJo": 0.61,
    "KTs": 0.66,
    "QJs": 0.68,
    "QJo": 0.59,
    "QTs": 0.64,
    "JTs": 0.64,
    "T9s": 0.58,
    "98s": 0.55,
    "87s": 0.52,
    "76s": 0.50,
    "65s": 0.49,
    "54s": 0.48,
}
