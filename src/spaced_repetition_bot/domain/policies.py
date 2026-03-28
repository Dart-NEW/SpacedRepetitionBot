"""Domain policies and strategy objects."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Protocol

from spaced_repetition_bot.domain.enums import (
    ReviewDirection,
    ReviewOutcome,
)
from spaced_repetition_bot.domain.models import ReviewTrack


class SpacedRepetitionPolicy(Protocol):
    """Contract for spaced repetition scheduling."""

    def initialize_tracks(self, now: datetime) -> tuple[ReviewTrack, ReviewTrack]:
        """Create initial review tracks."""

    def apply_outcome(
        self,
        track: ReviewTrack,
        now: datetime,
        outcome: ReviewOutcome,
    ) -> ReviewTrack:
        """Update a track after a review."""


@dataclass(frozen=True, slots=True)
class FixedIntervalSpacedRepetitionPolicy:
    """Fixed schedule that matches the assignment requirements."""

    intervals_days: tuple[int, ...] = (2, 3, 5, 7)

    def initialize_tracks(self, now: datetime) -> tuple[ReviewTrack, ReviewTrack]:
        """Create two review directions scheduled at the first interval."""

        return (
            ReviewTrack(
                direction=ReviewDirection.FORWARD,
                next_review_at=now + self._interval_delta(0),
            ),
            ReviewTrack(
                direction=ReviewDirection.REVERSE,
                next_review_at=now + self._interval_delta(0),
            ),
        )

    def apply_outcome(
        self,
        track: ReviewTrack,
        now: datetime,
        outcome: ReviewOutcome,
    ) -> ReviewTrack:
        """Advance or reset the track according to the answer."""

        if outcome is ReviewOutcome.INCORRECT:
            return replace(
                track,
                step_index=0,
                next_review_at=now + self._interval_delta(0),
                review_count=track.review_count + 1,
                last_outcome=outcome,
                completed_at=None,
            )
        return self._advance(track=track, now=now, outcome=outcome)

    def _advance(
        self,
        track: ReviewTrack,
        now: datetime,
        outcome: ReviewOutcome,
    ) -> ReviewTrack:
        next_step_index = track.step_index + 1
        if next_step_index >= len(self.intervals_days):
            return replace(
                track,
                step_index=len(self.intervals_days),
                next_review_at=None,
                review_count=track.review_count + 1,
                last_outcome=outcome,
                completed_at=now,
            )
        return replace(
            track,
            step_index=next_step_index,
            next_review_at=now + self._interval_delta(next_step_index),
            review_count=track.review_count + 1,
            last_outcome=outcome,
            completed_at=None,
        )

    def _interval_delta(self, step_index: int) -> timedelta:
        return timedelta(days=self.intervals_days[step_index])


class AnswerEvaluationPolicy(Protocol):
    """Contract for answer evaluation."""

    def is_correct(self, expected: str, provided: str) -> bool:
        """Return whether the provided answer should be accepted."""


@dataclass(frozen=True, slots=True)
class NormalizedTextAnswerPolicy:
    """Simple but deterministic normalization for manual answers."""

    def is_correct(self, expected: str, provided: str) -> bool:
        """Compare normalized strings."""

        return self.normalize(expected) == self.normalize(provided)

    @staticmethod
    def normalize(value: str) -> str:
        """Normalize user input for robust string comparison."""

        return " ".join(value.strip().casefold().split())
