from __future__ import annotations

import secrets

RANKS = "23456789TJQKA"
SUITS = "cdhs"

_SECURE_RANDOM = secrets.SystemRandom()


def new_deck() -> list[str]:
    return [rank + suit for suit in SUITS for rank in RANKS]


def shuffled_deck() -> list[str]:
    deck = new_deck()
    _SECURE_RANDOM.shuffle(deck)
    return deck

