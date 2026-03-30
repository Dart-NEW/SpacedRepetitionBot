"""Telegram quiz session domain model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from spaced_repetition_bot.domain.enums import ReviewDirection


@dataclass(frozen=True, slots=True)
class QuizReviewPointer:
    """A queued quiz review item inside a Telegram session."""

    card_id: UUID
    direction: ReviewDirection


@dataclass(frozen=True, slots=True)
class TelegramQuizSession:
    """Persistent active quiz session for a Telegram user."""

    user_id: int
    card_id: UUID
    direction: ReviewDirection
    started_at: datetime
    pending_reviews: tuple[QuizReviewPointer, ...] = ()
    total_prompts: int = 1
    due_reviews_total: int = 1
    answered_prompts: int = 0
    correct_prompts: int = 0
    incorrect_prompts: int = 0
    awaiting_start: bool = True
    message_id: int | None = None
