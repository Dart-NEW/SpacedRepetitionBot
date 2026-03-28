"""MVP repository adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from spaced_repetition_bot.domain.models import PhraseCard, UserSettings


@dataclass(slots=True)
class InMemoryPhraseRepository:
    """Simple in-memory storage for phrase cards."""

    _cards: dict[UUID, PhraseCard] = field(default_factory=dict)

    def add(self, card: PhraseCard) -> PhraseCard:
        """Persist a new card."""

        self._cards[card.id] = card
        return card

    def save(self, card: PhraseCard) -> PhraseCard:
        """Persist an updated card."""

        self._cards[card.id] = card
        return card

    def get(self, card_id: UUID) -> PhraseCard | None:
        """Fetch a card by identifier."""

        return self._cards.get(card_id)

    def list_by_user(self, user_id: int) -> list[PhraseCard]:
        """Return cards owned by a user."""

        return [card for card in self._cards.values() if card.user_id == user_id]


@dataclass(slots=True)
class InMemorySettingsRepository:
    """Simple in-memory storage for user settings."""

    _settings: dict[int, UserSettings] = field(default_factory=dict)

    def get(self, user_id: int) -> UserSettings | None:
        """Fetch settings by user id."""

        return self._settings.get(user_id)

    def save(self, settings: UserSettings) -> UserSettings:
        """Persist settings."""

        self._settings[settings.user_id] = settings
        return settings
