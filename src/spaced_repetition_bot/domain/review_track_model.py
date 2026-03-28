"""Review track domain model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from spaced_repetition_bot.domain.enums import (
    ReviewDirection,
    ReviewOutcome,
)


@dataclass(frozen=True, slots=True)
class ReviewTrack:
    """Progress for one review direction."""

    direction: ReviewDirection
    step_index: int = 0
    next_review_at: datetime | None = None
    review_count: int = 0
    last_outcome: ReviewOutcome | None = None
    completed_at: datetime | None = None

    @property
    def is_completed(self) -> bool:
        """Return whether the track has been completed."""

        return self.completed_at is not None

    def is_due(self, now: datetime) -> bool:
        """Return whether the track is due for review."""

        if self.is_completed or self.next_review_at is None:
            return False
        return self.next_review_at <= now
