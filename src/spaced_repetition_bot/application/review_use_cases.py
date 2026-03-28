"""Use cases for due reviews and answer submission."""

from __future__ import annotations

from dataclasses import dataclass

from spaced_repetition_bot.application.dto_reviews import (
    DueReviewItem,
    ReviewAnswerResult,
    SubmitReviewAnswerCommand,
)
from spaced_repetition_bot.application.errors import (
    LearningDisabledError,
    ReviewNotAvailableError,
)
from spaced_repetition_bot.application.ports import Clock, PhraseRepository
from spaced_repetition_bot.application.use_case_common import load_user_card
from spaced_repetition_bot.domain.enums import LearningStatus, ReviewOutcome
from spaced_repetition_bot.domain.policies import (
    AnswerEvaluationPolicy,
    SpacedRepetitionPolicy,
)


@dataclass(slots=True)
class GetDueReviewsUseCase:
    """Return due review prompts."""

    phrase_repository: PhraseRepository
    clock: Clock

    def execute(self, user_id: int) -> list[DueReviewItem]:
        now = self.clock.now()
        due_reviews: list[DueReviewItem] = []
        for card in self.phrase_repository.list_by_user(user_id):
            if card.learning_status is not LearningStatus.ACTIVE:
                continue
            for track in card.review_tracks:
                if not track.is_due(now):
                    continue
                due_reviews.append(
                    DueReviewItem(
                        card_id=card.id,
                        direction=track.direction,
                        prompt_text=card.prompt_for(track.direction),
                        due_at=track.next_review_at,
                        step_index=track.step_index,
                    )
                )
        return sorted(due_reviews, key=lambda item: item.due_at)


@dataclass(slots=True)
class SubmitReviewAnswerUseCase:
    """Evaluate an answer and update the schedule."""

    phrase_repository: PhraseRepository
    spaced_repetition_policy: SpacedRepetitionPolicy
    answer_evaluation_policy: AnswerEvaluationPolicy
    clock: Clock

    def execute(
        self, command: SubmitReviewAnswerCommand
    ) -> ReviewAnswerResult:
        card = load_user_card(
            self.phrase_repository, command.card_id, command.user_id
        )
        if card.learning_status is LearningStatus.NOT_LEARNING:
            raise LearningDisabledError(
                f"Card '{card.id}' is excluded from learning."
            )
        track = card.track_for(command.direction)
        now = self.clock.now()
        if not track.is_due(now):
            raise ReviewNotAvailableError(
                "Review for card "
                f"'{card.id}' and direction '{command.direction}' is not due."
            )
        expected = card.expected_answer_for(command.direction)
        outcome = self._evaluate(
            expected=expected, provided=command.answer_text
        )
        updated_track = self.spaced_repetition_policy.apply_outcome(
            track=track,
            now=now,
            outcome=outcome,
        )
        updated_card = self.phrase_repository.save(
            card.replace_track(updated_track)
        )
        return ReviewAnswerResult(
            card_id=updated_card.id,
            direction=command.direction,
            outcome=outcome,
            expected_answer=expected,
            provided_answer=command.answer_text,
            step_index=updated_track.step_index,
            next_review_at=updated_track.next_review_at,
            learning_status=updated_card.learning_status,
        )

    def _evaluate(self, expected: str, provided: str) -> ReviewOutcome:
        if self.answer_evaluation_policy.is_correct(
            expected=expected, provided=provided
        ):
            return ReviewOutcome.CORRECT
        return ReviewOutcome.INCORRECT
