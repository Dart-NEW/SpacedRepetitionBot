"""Typed commands, queries and result DTOs."""

# DTO map:
# - Gateway models describe adapter payloads returned by integrations.
# - Command models capture write-side intent from presentation layers.
# - Query models capture read-side requests from presentation layers.
# - Result models are immutable snapshots returned by use cases.
# - Translation DTOs cover provider output, user commands, and card results.
# - History DTOs expose recent saved cards without leaking entities.
# - Review DTOs represent due prompts and submitted answers.
# - Settings DTOs keep the public API separate from domain internals.
# - Progress DTOs aggregate counts for dashboards and API responses.
# - Quiz DTOs model prompt batches, summaries, and active-session answers.
# - These dataclasses are intentionally flat and serialization-friendly.
# - Use cases construct them, while presentation layers only read them.
# - Keeping them together makes cross-layer contracts easy to audit.
# - Field order mirrors the user-facing message or JSON payload order.
# - Optional fields appear only where a flow genuinely supports previews.
# - Enum-typed fields keep validation close to the application boundary.
# - No behavior lives here beyond dataclass defaults and structure.
# - Tests exercise these shapes through API, Telegram, and use-case flows.
# - When a contract changes, update this file before adapters.
# - The public import path remains stable for tests and runtime wiring.

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
    save_with_warning: bool = True
    history_entry_id: UUID | None = None


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

    history_entry_id: UUID
    card_id: UUID | None
    source_text: str
    translated_text: str
    direction: ReviewDirection
    source_lang: str
    target_lang: str
    learning_status: LearningStatus | None
    provider_name: str
    detected_source_lang: str | None
    is_identity_translation: bool
    has_pair_warning: bool
    saved: bool
    already_saved: bool
    scheduled_reviews: tuple[ScheduledReviewItem, ...]


@dataclass(frozen=True, slots=True)
class GetHistoryQuery:
    """History query."""

    user_id: int
    limit: int = 20


@dataclass(frozen=True, slots=True)
class HistoryItem:
    """Single history row."""

    id: UUID
    user_id: int
    card_id: UUID | None
    source_text: str
    translated_text: str
    source_lang: str
    target_lang: str
    created_at: datetime
    learning_status: LearningStatus | None
    saved: bool


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
    notification_frequency_days: int
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
    notification_frequency_days: int
    notifications_enabled: bool


@dataclass(frozen=True, slots=True)
class QuizSessionPrompt:
    """Current quiz prompt for a Telegram user."""

    card_id: UUID
    direction: ReviewDirection
    prompt_text: str
    expected_answer: str
    step_index: int
    session_position: int = 1
    total_prompts: int = 1


@dataclass(frozen=True, slots=True)
class QuizSessionStartResult:
    """Telegram quiz session state returned on start or resume."""

    prompt: QuizSessionPrompt
    due_reviews_total: int
    session_prompts_total: int
    awaiting_start: bool


@dataclass(frozen=True, slots=True)
class QuizSessionSummary:
    """Compact summary returned when a quiz session completes."""

    total_prompts: int
    answered_prompts: int
    correct_prompts: int
    incorrect_prompts: int
    remaining_due_reviews: int


@dataclass(frozen=True, slots=True)
class ActiveQuizAnswerResult:
    """Result of answering the current Telegram quiz prompt."""

    review_result: ReviewAnswerResult
    next_prompt: QuizSessionPrompt | None
    session_summary: QuizSessionSummary | None


@dataclass(frozen=True, slots=True)
class SkipQuizResult:
    """Result of skipping the current quiz card."""

    next_prompt: QuizSessionPrompt | None
    session_summary: QuizSessionSummary | None
