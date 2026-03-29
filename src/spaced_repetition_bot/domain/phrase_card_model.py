"""Phrase card domain model."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from spaced_repetition_bot.domain.enums import (
    LearningStatus,
    ReviewDirection,
)
from spaced_repetition_bot.domain.review_track_model import ReviewTrack


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

        return next(
            track
            for track in self.review_tracks
            if track.direction == direction
        )

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
            (
                updated_track
                if track.direction == updated_track.direction
                else track
            )
            for track in self.review_tracks
        )
        next_status = self.learning_status
        if next_status is not LearningStatus.NOT_LEARNING and all(
            track.is_completed for track in updated_tracks
        ):
            next_status = LearningStatus.LEARNED
        return replace(
            self, review_tracks=updated_tracks, learning_status=next_status
        )

    def disable_learning(self) -> PhraseCard:
        """Exclude a card from future reviews without deleting it."""

        return replace(
            self,
            learning_status=LearningStatus.NOT_LEARNING,
            archived_reason="user_opt_out",
        )

    def enable_learning(self) -> PhraseCard:
        """Re-enable learning for a card."""

        next_status = (
            LearningStatus.LEARNED
            if self.is_fully_learned
            else LearningStatus.ACTIVE
        )
        return replace(self, learning_status=next_status, archived_reason=None)
