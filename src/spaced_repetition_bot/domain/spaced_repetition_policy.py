"""Spaced repetition scheduling policy."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Literal, Protocol

from spaced_repetition_bot.domain.enums import (
    ReviewDirection,
    ReviewOutcome,
)
from spaced_repetition_bot.domain.review_track_model import ReviewTrack


class SpacedRepetitionPolicy(Protocol):
    """Contract for spaced repetition scheduling."""

    def initialize_tracks(
        self, now: datetime
    ) -> tuple[ReviewTrack, ReviewTrack]:
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

    intervals: tuple[int, ...] = (2, 3, 5, 7)
    interval_unit: Literal["days", "minutes"] = "days"

    def __post_init__(self) -> None:
        """Validate the configured schedule."""

        if not self.intervals:
            raise ValueError("Review intervals must not be empty.")
        if any(interval <= 0 for interval in self.intervals):
            raise ValueError("Review intervals must be positive.")

    def initialize_tracks(
        self, now: datetime
    ) -> tuple[ReviewTrack, ReviewTrack]:
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
        if next_step_index >= len(self.intervals):
            return replace(
                track,
                step_index=len(self.intervals),
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
        interval_value = self.intervals[step_index]
        if self.interval_unit == "minutes":
            return timedelta(minutes=interval_value)
        return timedelta(days=interval_value)
