from __future__ import annotations

import random

RANKS = "23456789TJQKA"
SUITS = "cdhs"


def new_deck() -> list[str]:
    return [rank + suit for suit in SUITS for rank in RANKS]


def shuffled_deck() -> list[str]:
    deck = new_deck()
    random.shuffle(deck)
    return deck

