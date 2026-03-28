"""Telegram quiz session domain model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from spaced_repetition_bot.domain.enums import ReviewDirection


@dataclass(frozen=True, slots=True)
class TelegramQuizSession:
    """Persistent active quiz session for a Telegram user."""

    user_id: int
    card_id: UUID
    direction: ReviewDirection
    started_at: datetime
