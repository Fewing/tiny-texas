from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.game.cards import shuffled_deck
from app.game.evaluator import describe, evaluate

WAITING = "waiting"
PREFLOP = "preflop"
FLOP = "flop"
TURN = "turn"
RIVER = "river"
BETTING_PHASES = {PREFLOP, FLOP, TURN, RIVER}


class GameError(ValueError):
    pass


@dataclass(frozen=True)
class RoomConfig:
    room_id: int
    code: str
    name: str
    seat_count: int
    small_blind: int
    big_blind: int
    buy_in: int


@dataclass
class PlayerRuntime:
    user_id: int
    username: str
    seat_index: int
    player_type: str = "human"
    stack: int = 0
    ready: bool = False
    connected: bool = False
    in_hand: bool = False
    folded: bool = False
    all_in: bool = False
    has_acted: bool = False
    current_bet: int = 0
    total_bet: int = 0
    hole_cards: list[str] = field(default_factory=list)

    def reset_for_hand(self) -> None:
        self.in_hand = True
        self.folded = False
        self.all_in = False
        self.has_acted = False
        self.current_bet = 0
        self.total_bet = 0
        self.hole_cards = []

    def commit(self, amount: int) -> int:
        actual = max(0, min(amount, self.stack))
        self.stack -= actual
        self.current_bet += actual
        self.total_bet += actual
        if self.stack == 0 and self.in_hand:
            self.all_in = True
        return actual


@dataclass(frozen=True)
class ActionEvent:
    sequence: int
    hand_number: int
    user_id: int | None
    seat_index: int | None
    phase: str
    action_type: str
    amount: int = 0
    payload: dict = field(default_factory=dict)

    def to_public(self) -> dict:
        return {
            "sequence": self.sequence,
            "hand_number": self.hand_number,
            "user_id": self.user_id,
            "seat_index": self.seat_index,
            "phase": self.phase,
            "action_type": self.action_type,
            "amount": self.amount,
            "payload": self.payload,
        }


@dataclass(frozen=True)
class HandResult:
    room_code: str
    hand_number: int
    reason: str
    pot: int
    community_cards: list[str]
    awards: list[dict]
    showdown_hands: dict[str, list[str]]
    summary: dict
    actions: list[ActionEvent]
    started_at: datetime
    ended_at: datetime

    def to_public(self) -> dict:
        return {
            "hand_number": self.hand_number,
            "reason": self.reason,
            "pot": self.pot,
            "community_cards": self.community_cards,
            "awards": self.awards,
            "showdown_hands": self.showdown_hands,
            "summary": self.summary,
        }


@dataclass
class RoomRuntime:
    config: RoomConfig
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    players: dict[int, PlayerRuntime] = field(default_factory=dict)
    phase: str = WAITING
    hand_number: int = 0
    dealer_seat: int | None = None
    current_turn_seat: int | None = None
    current_bet: int = 0
    min_raise: int = 0
    community_cards: list[str] = field(default_factory=list)
    deck: list[str] = field(default_factory=list)
    actions: list[ActionEvent] = field(default_factory=list)
    last_result: HandResult | None = None
    hand_started_at: datetime | None = None

    @property
    def code(self) -> str:
        return self.config.code

    @property
    def pot(self) -> int:
        return sum(player.total_bet for player in self.players.values())

    def seat_player(self, user_id: int, username: str, seat_index: int, player_type: str = "human") -> None:
        if self.phase != WAITING:
            raise GameError("Players can only take seats between hands.")
        if seat_index < 0 or seat_index >= self.config.seat_count:
            raise GameError("Invalid seat.")
        occupied = self.players.get(seat_index)
        if occupied is not None and occupied.user_id != user_id:
            raise GameError("Seat is already occupied.")
        for existing_seat, player in list(self.players.items()):
            if player.user_id == user_id and existing_seat != seat_index:
                del self.players[existing_seat]
        stack = occupied.stack if occupied is not None else self.config.buy_in
        ready = occupied.ready if occupied is not None else False
        self.players[seat_index] = PlayerRuntime(
            user_id=user_id,
            username=username,
            seat_index=seat_index,
            player_type=player_type,
            stack=stack,
            ready=ready,
        )

    def sync_seated_player(self, user_id: int, username: str, seat_index: int, player_type: str = "human") -> None:
        if seat_index < 0 or seat_index >= self.config.seat_count:
            return
        existing = self.players.get(seat_index)
        if existing is None:
            self.players[seat_index] = PlayerRuntime(
                user_id=user_id,
                username=username,
                seat_index=seat_index,
                player_type=player_type,
                stack=self.config.buy_in,
            )
        elif existing.user_id == user_id:
            existing.username = username
            existing.player_type = player_type

    def stand_player(self, user_id: int) -> None:
        seat_index = self._seat_for_user(user_id)
        if seat_index is None:
            return
        player = self.players[seat_index]
        if self.phase != WAITING and player.in_hand:
            raise GameError("Players can only stand between hands.")
        del self.players[seat_index]

    def set_connected(self, user_id: int, connected: bool) -> None:
        player = self._player_for_user(user_id)
        if player is not None:
            player.connected = connected

    def set_ready(self, user_id: int, ready: bool = True) -> None:
        if self.phase != WAITING:
            raise GameError("Ready state can only change between hands.")
        player = self._player_for_user(user_id)
        if player is None:
            raise GameError("Take a seat before getting ready.")
        if player.stack <= 0:
            player.stack = self.config.buy_in
        player.ready = ready

    def start_hand(self) -> HandResult | None:
        if self.phase != WAITING:
            raise GameError("A hand is already in progress.")
        active_seats = [seat for seat, player in sorted(self.players.items()) if player.ready and player.stack > 0]
        if len(active_seats) < 2:
            raise GameError("At least two ready seated players are required.")

        self.hand_number += 1
        self.phase = PREFLOP
        self.current_turn_seat = None
        self.current_bet = 0
        self.min_raise = self.config.big_blind
        self.community_cards = []
        self.deck = shuffled_deck()
        self.actions = []
        self.last_result = None
        self.hand_started_at = datetime.now(timezone.utc)

        for seat in active_seats:
            self.players[seat].reset_for_hand()

        self.dealer_seat = self._next_seat_after(
            self.dealer_seat if self.dealer_seat is not None else active_seats[-1],
            lambda seat: seat in active_seats,
        )
        if self.dealer_seat is None:
            raise GameError("Could not assign dealer.")

        small_blind_seat = (
            self.dealer_seat
            if len(active_seats) == 2
            else self._next_seat_after(self.dealer_seat, lambda seat: seat in active_seats)
        )
        big_blind_seat = self._next_seat_after(small_blind_seat, lambda seat: seat in active_seats)
        if small_blind_seat is None or big_blind_seat is None:
            raise GameError("Could not assign blinds.")

        for _round in range(2):
            for seat in self._ordered_from(small_blind_seat, active_seats):
                self.players[seat].hole_cards.append(self.deck.pop())

        self._post_blind(small_blind_seat, "small_blind", self.config.small_blind)
        self._post_blind(big_blind_seat, "big_blind", self.config.big_blind)
        self.current_bet = max(player.current_bet for player in self.players.values() if player.in_hand)
        self.current_turn_seat = self._next_actor_after(big_blind_seat)
        if self.current_turn_seat is None:
            return self._advance_streets_until_action_or_finish()
        return None

    def legal_actions_for_user(self, user_id: int) -> list[dict]:
        player = self._player_for_user(user_id)
        if player is None or self.phase not in BETTING_PHASES or self.current_turn_seat != player.seat_index:
            return []

        to_call = max(0, self.current_bet - player.current_bet)
        max_total = player.current_bet + player.stack
        actions: list[dict] = []
        if to_call > 0:
            actions.append({"type": "fold", "amount": 0})
            actions.append({"type": "call", "amount": min(to_call, player.stack), "to_call": to_call})
            if max_total > self.current_bet:
                min_total = self.current_bet + self.min_raise
                if max_total >= min_total:
                    actions.append({"type": "raise", "min": min_total, "max": max_total})
            if player.stack > 0:
                actions.append({"type": "all_in", "amount": max_total})
            return actions

        actions.append({"type": "check", "amount": 0})
        if player.stack >= self.config.big_blind:
            actions.append({"type": "bet", "min": self.config.big_blind, "max": max_total})
        if player.stack > 0:
            actions.append({"type": "all_in", "amount": max_total})
        return actions

    def submit_action(self, user_id: int, action_type: str, amount: int = 0) -> HandResult | None:
        player = self._player_for_user(user_id)
        if player is None or player.seat_index != self.current_turn_seat:
            raise GameError("It is not your turn.")
        legal_types = {action["type"] for action in self.legal_actions_for_user(user_id)}
        if action_type not in legal_types:
            raise GameError("Illegal action.")

        old_current_bet = self.current_bet
        committed = 0
        target_total = 0
        to_call = max(0, self.current_bet - player.current_bet)

        if action_type == "fold":
            player.folded = True
        elif action_type == "check":
            if to_call:
                raise GameError("Cannot check facing a bet.")
        elif action_type == "call":
            committed = player.commit(to_call)
        elif action_type == "bet":
            if self.current_bet != 0:
                raise GameError("Use raise when a bet already exists.")
            target_total = int(amount)
            if target_total < self.config.big_blind:
                raise GameError("Bet is below the minimum.")
            if target_total > player.current_bet + player.stack:
                raise GameError("Bet exceeds stack.")
            committed = player.commit(target_total - player.current_bet)
            self.current_bet = player.current_bet
            self.min_raise = max(self.config.big_blind, self.current_bet)
        elif action_type == "raise":
            target_total = int(amount)
            min_total = self.current_bet + self.min_raise
            if target_total < min_total:
                raise GameError("Raise is below the minimum.")
            if target_total > player.current_bet + player.stack:
                raise GameError("Raise exceeds stack.")
            committed = player.commit(target_total - player.current_bet)
            self.current_bet = player.current_bet
            self.min_raise = max(self.min_raise, self.current_bet - old_current_bet)
        elif action_type == "all_in":
            committed = player.commit(player.stack)
            if player.current_bet > self.current_bet:
                self.current_bet = player.current_bet
                raise_size = self.current_bet - old_current_bet
                if raise_size >= self.min_raise:
                    self.min_raise = raise_size

        if self.current_bet > old_current_bet:
            for other in self.players.values():
                if other.user_id != player.user_id and self._can_act(other):
                    other.has_acted = False
        player.has_acted = True
        self._record_action(player.user_id, player.seat_index, action_type, committed or target_total, {"target": target_total})
        return self._advance_after_player_action(player.seat_index)

    def public_state(self, viewer_user_id: int | None = None) -> dict:
        seats = []
        for seat_index in range(self.config.seat_count):
            player = self.players.get(seat_index)
            if player is None:
                seats.append({"seat_index": seat_index, "occupied": False})
                continue
            hole_cards: list[str] = []
            if player.in_hand and player.hole_cards:
                hole_cards = player.hole_cards if player.user_id == viewer_user_id else ["XX", "XX"]
            seats.append(
                {
                    "seat_index": seat_index,
                    "occupied": True,
                    "user_id": player.user_id,
                    "username": player.username,
                    "player_type": player.player_type,
                    "stack": player.stack,
                    "ready": player.ready,
                    "connected": player.connected,
                    "in_hand": player.in_hand,
                    "folded": player.folded,
                    "all_in": player.all_in,
                    "current_bet": player.current_bet,
                    "total_bet": player.total_bet,
                    "hole_cards": hole_cards,
                }
            )
        return {
            "room": {
                "id": self.config.room_id,
                "code": self.config.code,
                "name": self.config.name,
                "seat_count": self.config.seat_count,
                "small_blind": self.config.small_blind,
                "big_blind": self.config.big_blind,
                "buy_in": self.config.buy_in,
            },
            "phase": self.phase,
            "hand_number": self.hand_number,
            "dealer_seat": self.dealer_seat,
            "current_turn_seat": self.current_turn_seat,
            "current_bet": self.current_bet,
            "pot": self.pot,
            "community_cards": self.community_cards,
            "players": seats,
            "legal_actions": self.legal_actions_for_user(viewer_user_id) if viewer_user_id else [],
            "can_start": self.phase == WAITING and len(self._ready_seats()) >= 2,
            "last_result": self.last_result.to_public() if self.last_result else None,
            "actions": [event.to_public() for event in self.actions[-20:]],
            "viewer_user_id": viewer_user_id,
        }

    def _post_blind(self, seat_index: int, action_type: str, blind: int) -> None:
        player = self.players[seat_index]
        posted = player.commit(blind)
        self._record_action(player.user_id, seat_index, action_type, posted, {"blind": blind})

    def _advance_after_player_action(self, actor_seat: int) -> HandResult | None:
        if len(self._nonfolded_players()) == 1:
            return self._finish_by_fold()
        if self._betting_round_complete():
            return self._advance_streets_until_action_or_finish()
        self.current_turn_seat = self._next_actor_after(actor_seat)
        return None

    def _advance_streets_until_action_or_finish(self) -> HandResult | None:
        while True:
            if len(self._nonfolded_players()) == 1:
                return self._finish_by_fold()
            if self.phase == RIVER:
                return self._finish_showdown()
            self._begin_next_street()
            actors = [seat for seat, player in self.players.items() if self._can_act(player)]
            if len(actors) <= 1:
                continue
            self.current_turn_seat = self._next_seat_after(self.dealer_seat, lambda seat: seat in actors)
            return None

    def _begin_next_street(self) -> None:
        if self.phase == PREFLOP:
            self.phase = FLOP
            self.community_cards.extend([self.deck.pop(), self.deck.pop(), self.deck.pop()])
        elif self.phase == FLOP:
            self.phase = TURN
            self.community_cards.append(self.deck.pop())
        elif self.phase == TURN:
            self.phase = RIVER
            self.community_cards.append(self.deck.pop())
        for player in self.players.values():
            if player.in_hand:
                player.current_bet = 0
                player.has_acted = False
        self.current_bet = 0
        self.min_raise = self.config.big_blind
        self.current_turn_seat = None
        self._record_action(None, None, f"deal_{self.phase}", 0, {"community_cards": list(self.community_cards)})

    def _betting_round_complete(self) -> bool:
        actors = [player for player in self.players.values() if self._can_act(player)]
        if not actors:
            return True
        return all(player.has_acted and player.current_bet == self.current_bet for player in actors)

    def _finish_by_fold(self) -> HandResult:
        winner = self._nonfolded_players()[0]
        pot = self.pot
        winner.stack += pot
        awards = [
            {
                "user_id": winner.user_id,
                "username": winner.username,
                "seat_index": winner.seat_index,
                "amount": pot,
                "hand_rank": "uncontested",
            }
        ]
        return self._complete_hand("fold", pot, awards, {})

    def _finish_showdown(self) -> HandResult:
        values = {
            player.seat_index: evaluate(player.hole_cards + self.community_cards)
            for player in self._nonfolded_players()
        }
        contributions = {
            seat: player.total_bet
            for seat, player in self.players.items()
            if player.in_hand and player.total_bet > 0
        }
        awards_by_seat: dict[int, int] = defaultdict(int)
        previous = 0
        for level in sorted(set(contributions.values())):
            participants = [seat for seat, total in contributions.items() if total >= level]
            side_pot = (level - previous) * len(participants)
            eligible = [seat for seat in participants if seat in values]
            if eligible:
                best = max(values[seat] for seat in eligible)
                winners = sorted(seat for seat in eligible if values[seat] == best)
                share = side_pot // len(winners)
                remainder = side_pot % len(winners)
                for winner_seat in winners:
                    awards_by_seat[winner_seat] += share + (1 if remainder > 0 else 0)
                    remainder -= 1 if remainder > 0 else 0
            previous = level

        awards = []
        for seat, amount in sorted(awards_by_seat.items()):
            player = self.players[seat]
            player.stack += amount
            value = values[seat]
            awards.append(
                {
                    "user_id": player.user_id,
                    "username": player.username,
                    "seat_index": seat,
                    "amount": amount,
                    "hand_rank": describe(value),
                }
            )
        showdown_hands = {
            str(player.user_id): list(player.hole_cards)
            for player in self._nonfolded_players()
        }
        return self._complete_hand("showdown", self.pot, awards, showdown_hands)

    def _complete_hand(
        self,
        reason: str,
        pot: int,
        awards: list[dict],
        showdown_hands: dict[str, list[str]],
    ) -> HandResult:
        ended_at = datetime.now(timezone.utc)
        result = HandResult(
            room_code=self.config.code,
            hand_number=self.hand_number,
            reason=reason,
            pot=pot,
            community_cards=list(self.community_cards),
            awards=awards,
            showdown_hands=showdown_hands,
            summary={
                "dealer_seat": self.dealer_seat,
                "small_blind": self.config.small_blind,
                "big_blind": self.config.big_blind,
            },
            actions=list(self.actions),
            started_at=self.hand_started_at or ended_at,
            ended_at=ended_at,
        )
        self.last_result = result
        self.phase = WAITING
        self.current_turn_seat = None
        self.current_bet = 0
        self.min_raise = self.config.big_blind
        for player in self.players.values():
            if player.in_hand:
                player.ready = False
            player.in_hand = False
            player.folded = False
            player.all_in = False
            player.has_acted = False
            player.current_bet = 0
            player.total_bet = 0
            player.hole_cards = []
        return result

    def _record_action(
        self,
        user_id: int | None,
        seat_index: int | None,
        action_type: str,
        amount: int = 0,
        payload: dict | None = None,
    ) -> None:
        self.actions.append(
            ActionEvent(
                sequence=len(self.actions) + 1,
                hand_number=self.hand_number,
                user_id=user_id,
                seat_index=seat_index,
                phase=self.phase,
                action_type=action_type,
                amount=amount,
                payload=payload or {},
            )
        )

    def _ready_seats(self) -> list[int]:
        return [seat for seat, player in self.players.items() if player.ready and player.stack > 0]

    def _nonfolded_players(self) -> list[PlayerRuntime]:
        return [player for player in self.players.values() if player.in_hand and not player.folded]

    def _can_act(self, player: PlayerRuntime) -> bool:
        return player.in_hand and not player.folded and not player.all_in

    def _player_for_user(self, user_id: int | None) -> PlayerRuntime | None:
        for player in self.players.values():
            if player.user_id == user_id:
                return player
        return None

    def _seat_for_user(self, user_id: int) -> int | None:
        for seat, player in self.players.items():
            if player.user_id == user_id:
                return seat
        return None

    def _next_actor_after(self, seat_index: int | None) -> int | None:
        return self._next_seat_after(seat_index, lambda seat: self._can_act(self.players[seat]))

    def _next_seat_after(self, seat_index: int | None, predicate) -> int | None:
        start = -1 if seat_index is None else seat_index
        for offset in range(1, self.config.seat_count + 1):
            candidate = (start + offset) % self.config.seat_count
            if candidate in self.players and predicate(candidate):
                return candidate
        return None

    def _ordered_from(self, start_seat: int, seats: list[int]) -> list[int]:
        seat_set = set(seats)
        ordered = []
        for offset in range(self.config.seat_count):
            candidate = (start_seat + offset) % self.config.seat_count
            if candidate in seat_set:
                ordered.append(candidate)
        return ordered
