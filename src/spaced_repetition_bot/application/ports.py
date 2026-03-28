"""Ports used by the application layer."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from spaced_repetition_bot.application.dtos import TranslationGatewayResult
from spaced_repetition_bot.domain.models import PhraseCard, UserSettings


class Clock(Protocol):
    """Time provider."""

    def now(self) -> datetime:
        """Return current datetime."""


class PhraseRepository(Protocol):
    """Card storage port."""

    def add(self, card: PhraseCard) -> PhraseCard:
        """Persist a new card."""

    def save(self, card: PhraseCard) -> PhraseCard:
        """Persist an existing card."""

    def get(self, card_id: UUID) -> PhraseCard | None:
        """Fetch a card by id."""

    def list_by_user(self, user_id: int) -> list[PhraseCard]:
        """Return all cards for a user."""


class SettingsRepository(Protocol):
    """User settings storage port."""

    def get(self, user_id: int) -> UserSettings | None:
        """Fetch settings for a user."""

    def save(self, settings: UserSettings) -> UserSettings:
        """Persist settings."""


class TranslationProvider(Protocol):
    """External translation contract."""

    def translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
    ) -> TranslationGatewayResult:
        """Translate text between languages."""
