from __future__ import annotations

from typing import Protocol

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

