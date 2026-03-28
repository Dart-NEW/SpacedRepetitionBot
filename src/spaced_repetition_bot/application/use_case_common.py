"""Shared helpers for application use cases."""

from __future__ import annotations

from uuid import UUID

from spaced_repetition_bot.application.dto_settings import UserSettingsSnapshot
from spaced_repetition_bot.application.dto_translation import (
    ScheduledReviewItem,
)
from spaced_repetition_bot.application.errors import CardNotFoundError
from spaced_repetition_bot.application.ports import PhraseRepository
from spaced_repetition_bot.domain.models import PhraseCard, UserSettings


def default_settings(user_id: int) -> UserSettings:
    """Return default user settings."""

    return UserSettings(user_id=user_id)


def map_settings_snapshot(settings: UserSettings) -> UserSettingsSnapshot:
    """Convert settings to an external DTO."""

    return UserSettingsSnapshot(
        user_id=settings.user_id,
        default_source_lang=settings.default_source_lang,
        default_target_lang=settings.default_target_lang,
        timezone=settings.timezone,
        notification_time_local=settings.notification_time_local,
        notifications_enabled=settings.notifications_enabled,
    )


def map_scheduled_review(track) -> ScheduledReviewItem:
    """Convert a track to a schedule DTO."""

    return ScheduledReviewItem(
        direction=track.direction,
        step_index=track.step_index,
        next_review_at=track.next_review_at,
        completed=track.is_completed,
    )


def load_user_card(
    repository: PhraseRepository, card_id: UUID, user_id: int
) -> PhraseCard:
    """Load a card and ensure it belongs to the user."""

    card = repository.get(card_id)
    if card is None or card.user_id != user_id:
        raise CardNotFoundError(
            f"Card '{card_id}' was not found for user '{user_id}'."
        )
    return card
