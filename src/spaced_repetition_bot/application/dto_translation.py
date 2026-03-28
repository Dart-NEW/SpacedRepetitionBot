"""Translation-related application DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from spaced_repetition_bot.domain.enums import (
    LearningStatus,
    ReviewDirection,
)


@dataclass(frozen=True, slots=True)
class TranslationGatewayResult:
    """External translation payload returned by a provider."""

    translated_text: str
    provider_name: str
    detected_source_lang: str | None = None


@dataclass(frozen=True, slots=True)
class TranslatePhraseCommand:
    """Command for translating and optionally scheduling a phrase."""

    user_id: int
    text: str
    source_lang: str | None = None
    target_lang: str | None = None
    learn: bool = True


@dataclass(frozen=True, slots=True)
class ScheduledReviewItem:
    """Review schedule details returned to the caller."""

    direction: ReviewDirection
    step_index: int
    next_review_at: datetime | None
    completed: bool


@dataclass(frozen=True, slots=True)
class TranslationResult:
    """Result of translation and card creation."""

    card_id: UUID
    source_text: str
    translated_text: str
    source_lang: str
    target_lang: str
    learning_status: LearningStatus
    provider_name: str
    scheduled_reviews: tuple[ScheduledReviewItem, ScheduledReviewItem]
