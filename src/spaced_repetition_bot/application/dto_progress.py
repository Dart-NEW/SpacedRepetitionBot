"""Progress-related application DTOs."""

from __future__ import annotations

from dataclasses import dataclass


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
