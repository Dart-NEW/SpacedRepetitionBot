"""Use case for user progress aggregation."""

from __future__ import annotations

from dataclasses import dataclass

from spaced_repetition_bot.application.dto_progress import (
    GetUserProgressQuery,
    UserProgressSnapshot,
)
from spaced_repetition_bot.application.ports import Clock, PhraseRepository
from spaced_repetition_bot.domain.enums import LearningStatus
from spaced_repetition_bot.domain.models import PhraseCard


@dataclass(slots=True)
class GetUserProgressUseCase:
    """Aggregate user progress."""

    phrase_repository: PhraseRepository
    clock: Clock

    def execute(self, query: GetUserProgressQuery) -> UserProgressSnapshot:
        cards = self.phrase_repository.list_by_user(query.user_id)
        now = self.clock.now()
        return UserProgressSnapshot(
            total_cards=len(cards),
            active_cards=self._count_cards(cards, LearningStatus.ACTIVE),
            learned_cards=self._count_cards(cards, LearningStatus.LEARNED),
            not_learning_cards=self._count_cards(
                cards, LearningStatus.NOT_LEARNING
            ),
            due_reviews=self._count_due_reviews(cards, now),
            completed_review_tracks=self._count_completed_tracks(cards),
            total_review_tracks=self._count_total_tracks(cards),
        )

    @staticmethod
    def _count_cards(cards: list[PhraseCard], status: LearningStatus) -> int:
        return sum(card.learning_status is status for card in cards)

    @staticmethod
    def _count_due_reviews(cards: list[PhraseCard], now) -> int:
        return sum(
            track.is_due(now)
            for card in cards
            if card.learning_status is LearningStatus.ACTIVE
            for track in card.review_tracks
        )

    @staticmethod
    def _count_completed_tracks(cards: list[PhraseCard]) -> int:
        return sum(
            track.is_completed
            for card in cards
            for track in card.review_tracks
        )

    @staticmethod
    def _count_total_tracks(cards: list[PhraseCard]) -> int:
        return sum(len(card.review_tracks) for card in cards)
