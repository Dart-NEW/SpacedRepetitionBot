"""Core domain models."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, time
from uuid import UUID

from spaced_repetition_bot.domain.enums import (
    LearningStatus,
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


@dataclass(frozen=True, slots=True)
class PhraseCard:
    """A translated phrase stored for learning."""

    id: UUID
    user_id: int
    source_text: str
    target_text: str
    source_lang: str
    target_lang: str
    created_at: datetime
    learning_status: LearningStatus
    review_tracks: tuple[ReviewTrack, ReviewTrack]
    archived_reason: str | None = None

    def track_for(self, direction: ReviewDirection) -> ReviewTrack:
        """Return the track for a review direction."""

        return next(track for track in self.review_tracks if track.direction == direction)

    def prompt_for(self, direction: ReviewDirection) -> str:
        """Return the prompt text shown to the learner."""

        if direction is ReviewDirection.FORWARD:
            return self.source_text
        return self.target_text

    def expected_answer_for(self, direction: ReviewDirection) -> str:
        """Return the expected answer for a direction."""

        if direction is ReviewDirection.FORWARD:
            return self.target_text
        return self.source_text

    @property
    def is_fully_learned(self) -> bool:
        """Return whether both directions have been completed."""

        return all(track.is_completed for track in self.review_tracks)

    def replace_track(self, updated_track: ReviewTrack) -> PhraseCard:
        """Return a new card with one track replaced."""

        updated_tracks = tuple(
            updated_track if track.direction == updated_track.direction else track
            for track in self.review_tracks
        )
        next_status = self.learning_status
        if next_status is not LearningStatus.NOT_LEARNING and all(
            track.is_completed for track in updated_tracks
        ):
            next_status = LearningStatus.LEARNED
        return replace(self, review_tracks=updated_tracks, learning_status=next_status)

    def disable_learning(self) -> PhraseCard:
        """Exclude a card from future reviews without deleting it."""

        return replace(
            self,
            learning_status=LearningStatus.NOT_LEARNING,
            archived_reason="user_opt_out",
        )

    def enable_learning(self) -> PhraseCard:
        """Re-enable learning for a card."""

        next_status = LearningStatus.LEARNED if self.is_fully_learned else LearningStatus.ACTIVE
        return replace(self, learning_status=next_status, archived_reason=None)


@dataclass(frozen=True, slots=True)
class UserSettings:
    """User-facing preferences."""

    user_id: int
    default_source_lang: str = "en"
    default_target_lang: str = "es"
    timezone: str = "UTC"
    notification_time_local: time = time(hour=9, minute=0)
    notifications_enabled: bool = True
