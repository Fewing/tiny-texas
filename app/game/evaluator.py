from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

RANK_VALUE = {rank: value for value, rank in enumerate("23456789TJQKA", start=2)}
HAND_NAMES = {
    8: "同花顺",
    7: "四条",
    6: "葫芦",
    5: "同花",
    4: "顺子",
    3: "三条",
    2: "两对",
    1: "一对",
    0: "高牌",
}


@dataclass(frozen=True, order=True)
class HandValue:
    category: int
    kickers: tuple[int, ...]

    @property
    def name(self) -> str:
        return HAND_NAMES[self.category]


def _rank(card: str) -> int:
    return RANK_VALUE[card[0]]


def _suit(card: str) -> str:
    return card[1]


def _straight_high(ranks: list[int]) -> int | None:
    unique = sorted(set(ranks), reverse=True)
    if 14 in unique:
        unique.append(1)
    run = 1
    for index in range(1, len(unique)):
        if unique[index - 1] - 1 == unique[index]:
            run += 1
            if run >= 5:
                return unique[index - 4]
        elif unique[index - 1] != unique[index]:
            run = 1
    return None


def evaluate(cards: list[str]) -> HandValue:
    if len(cards) < 5:
        raise ValueError("至少需要五张牌。")

    ranks = [_rank(card) for card in cards]
    counts = Counter(ranks)
    ranks_by_suit: dict[str, list[int]] = defaultdict(list)
    for card in cards:
        ranks_by_suit[_suit(card)].append(_rank(card))

    flush_ranks = None
    for suited_ranks in ranks_by_suit.values():
        if len(suited_ranks) >= 5:
            flush_ranks = sorted(suited_ranks, reverse=True)
            break

    if flush_ranks:
        straight_flush_high = _straight_high(flush_ranks)
        if straight_flush_high:
            return HandValue(8, (straight_flush_high,))

    groups = sorted(counts.items(), key=lambda item: (item[1], item[0]), reverse=True)
    quads = [rank for rank, count in groups if count == 4]
    if quads:
        quad = quads[0]
        kicker = max(rank for rank in ranks if rank != quad)
        return HandValue(7, (quad, kicker))

    trips = sorted([rank for rank, count in counts.items() if count == 3], reverse=True)
    pairs = sorted([rank for rank, count in counts.items() if count == 2], reverse=True)
    if trips and (len(trips) > 1 or pairs):
        trip = trips[0]
        pair = trips[1] if len(trips) > 1 else pairs[0]
        return HandValue(6, (trip, pair))

    if flush_ranks:
        return HandValue(5, tuple(flush_ranks[:5]))

    straight_high = _straight_high(ranks)
    if straight_high:
        return HandValue(4, (straight_high,))

    if trips:
        trip = trips[0]
        kickers = sorted([rank for rank in ranks if rank != trip], reverse=True)[:2]
        return HandValue(3, (trip, *kickers))

    if len(pairs) >= 2:
        top_pairs = pairs[:2]
        kicker = max(rank for rank in ranks if rank not in top_pairs)
        return HandValue(2, (*top_pairs, kicker))

    if len(pairs) == 1:
        pair = pairs[0]
        kickers = sorted([rank for rank in ranks if rank != pair], reverse=True)[:3]
        return HandValue(1, (pair, *kickers))

    return HandValue(0, tuple(sorted(ranks, reverse=True)[:5]))


def describe(value: HandValue) -> str:
    return value.name
