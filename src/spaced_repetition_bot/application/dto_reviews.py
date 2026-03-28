"""Review-related application DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from spaced_repetition_bot.domain.enums import (
    LearningStatus,
    ReviewDirection,
    ReviewOutcome,
)


@dataclass(frozen=True, slots=True)
class DueReviewItem:
    """Single due review prompt."""

    card_id: UUID
    direction: ReviewDirection
    prompt_text: str
    due_at: datetime
    step_index: int


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
