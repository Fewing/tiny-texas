from app.game import cards


class ReversingRandom:
    def __init__(self) -> None:
        self.shuffle_calls = 0

    def shuffle(self, deck: list[str]) -> None:
        self.shuffle_calls += 1
        deck.reverse()


def test_shuffled_deck_uses_secure_random_source(monkeypatch) -> None:
    secure_random = ReversingRandom()
    monkeypatch.setattr(cards, "_SECURE_RANDOM", secure_random)

    deck = cards.shuffled_deck()

    assert secure_random.shuffle_calls == 1
    assert deck == list(reversed(cards.new_deck()))
    assert len(deck) == 52
    assert len(set(deck)) == 52
