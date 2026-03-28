"""History-related application DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from spaced_repetition_bot.domain.enums import LearningStatus


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
