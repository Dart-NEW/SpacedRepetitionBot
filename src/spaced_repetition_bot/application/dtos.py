"""Typed commands, queries and result DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from uuid import UUID

from spaced_repetition_bot.domain.enums import (
    LearningStatus,
    ReviewDirection,
    ReviewOutcome,
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
    direction: ReviewDirection | None = None
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
    direction: ReviewDirection
    source_lang: str
    target_lang: str
    learning_status: LearningStatus
    provider_name: str
    scheduled_reviews: tuple[ScheduledReviewItem, ScheduledReviewItem]


@dataclass(frozen=True, slots=True)
class GetHistoryQuery:
    """History query."""

    user_id: int
    limit: int = 20


@dataclass(frozen=True, slots=True)
class HistoryItem:
    """Single history row."""

    card_id: UUID
    source_text: str
    translated_text: str
    source_lang: str
    target_lang: str
    created_at: datetime
    learning_status: LearningStatus


@dataclass(frozen=True, slots=True)
class ToggleLearningCommand:
    """Command for enabling or disabling learning."""

    user_id: int
    card_id: UUID
    learning_enabled: bool


@dataclass(frozen=True, slots=True)
class DueReviewItem:
    """Single due review prompt."""

    card_id: UUID
    direction: ReviewDirection
    prompt_text: str
    due_at: datetime
    step_index: int


@dataclass(frozen=True, slots=True)
class GetUserProgressQuery:
    """Progress query."""

    user_id: int


@dataclass(frozen=True, slots=True)
class UserProgressSnapshot:
    """Aggregated progress metrics."""

    total_cards: int
    active_cards: int
    learned_cards: int
    not_learning_cards: int
    due_reviews: int
    completed_review_tracks: int
    total_review_tracks: int


@dataclass(frozen=True, slots=True)
class SubmitReviewAnswerCommand:
    """Command for submitting a manual review answer."""

    user_id: int
    card_id: UUID
    direction: ReviewDirection
    answer_text: str


@dataclass(frozen=True, slots=True)
class ReviewAnswerResult:
    """Result of review submission."""

    card_id: UUID
    direction: ReviewDirection
    outcome: ReviewOutcome
    expected_answer: str
    provided_answer: str
    step_index: int
    next_review_at: datetime | None
    learning_status: LearningStatus


@dataclass(frozen=True, slots=True)
class GetSettingsQuery:
    """Query for user settings."""

    user_id: int


@dataclass(frozen=True, slots=True)
class UserSettingsSnapshot:
    """Public settings DTO."""

    user_id: int
    default_source_lang: str
    default_target_lang: str
    default_translation_direction: ReviewDirection
    timezone: str
    notification_time_local: time
    notifications_enabled: bool


@dataclass(frozen=True, slots=True)
class UpdateSettingsCommand:
    """Command for updating settings."""

    user_id: int
    default_source_lang: str
    default_target_lang: str
    default_translation_direction: ReviewDirection
    timezone: str
    notification_time_local: time
    notifications_enabled: bool


@dataclass(frozen=True, slots=True)
class QuizSessionPrompt:
    """Current quiz prompt for a Telegram user."""

    card_id: UUID
    direction: ReviewDirection
    prompt_text: str
    expected_answer: str
    step_index: int


@dataclass(frozen=True, slots=True)
class ActiveQuizAnswerResult:
    """Result of answering the current Telegram quiz prompt."""

    review_result: ReviewAnswerResult
    next_prompt: QuizSessionPrompt | None
