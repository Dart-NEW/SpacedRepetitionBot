"""Quiz-session application use cases.

This module contains the persistent Telegram quiz workflow. It depends on the
shared helpers from `_use_cases_core` and is re-exported through the public
`application.use_cases` compatibility module.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from spaced_repetition_bot.application.dtos import (
    ActiveQuizAnswerResult,
    QuizSessionStartResult,
    SkipQuizResult,
    SubmitReviewAnswerCommand,
)
from spaced_repetition_bot.application.errors import (
    CardNotFoundError,
    QuizSessionNotFoundError,
)
from spaced_repetition_bot.application.ports import (
    Clock,
    PhraseRepository,
    QuizSessionRepository,
)
from spaced_repetition_bot.application._use_cases_core import (
    QUIZ_SESSION_LIMIT,
    SubmitReviewAnswerUseCase,
    build_quiz_prompt,
    build_quiz_summary,
    list_due_reviews,
    load_user_card,
    mix_due_reviews,
)
from spaced_repetition_bot.domain.enums import (
    LearningStatus,
    ReviewOutcome,
)
from spaced_repetition_bot.domain.models import (
    QuizReviewPointer,
    TelegramQuizSession,
)


@dataclass(slots=True)
class StartQuizSessionUseCase:
    """Start or resume a persistent Telegram quiz session."""

    phrase_repository: PhraseRepository
    quiz_session_repository: QuizSessionRepository
    clock: Clock

    def execute(
        self,
        user_id: int,
        *,
        activate: bool = False,
        message_id: int | None = None,
    ):
        existing = self.quiz_session_repository.get(user_id)
        if existing is not None:
            session = self._resume(existing)
            if session is not None:
                session = self._activate_session(
                    session=session,
                    activate=activate,
                    message_id=message_id,
                )
                return self._build_start_result(session)
            self.quiz_session_repository.delete(user_id)
        due_reviews = mix_due_reviews(
            list_due_reviews(
                phrase_repository=self.phrase_repository,
                user_id=user_id,
                now=self.clock.now(),
            )
        )
        if not due_reviews:
            return None
        session_reviews = due_reviews[:QUIZ_SESSION_LIMIT]
        first_review = session_reviews[0]
        session = TelegramQuizSession(
            user_id=user_id,
            card_id=first_review.card_id,
            direction=first_review.direction,
            started_at=self.clock.now(),
            pending_reviews=tuple(
                QuizReviewPointer(
                    card_id=item.card_id,
                    direction=item.direction,
                )
                for item in session_reviews[1:]
            ),
            total_prompts=len(session_reviews),
            due_reviews_total=len(due_reviews),
            awaiting_start=not activate,
            message_id=message_id,
        )
        session = self.quiz_session_repository.save(session)
        return self._build_start_result(session)

    def _build_start_result(self, session: TelegramQuizSession):
        return QuizSessionStartResult(
            prompt=self._build_prompt(session),
            due_reviews_total=session.due_reviews_total,
            session_prompts_total=session.total_prompts,
            awaiting_start=session.awaiting_start,
        )

    def _resume(
        self, session: TelegramQuizSession
    ) -> TelegramQuizSession | None:
        try:
            card = load_user_card(
                self.phrase_repository, session.card_id, session.user_id
            )
        except CardNotFoundError:
            return None
        if card.learning_status is not LearningStatus.ACTIVE:
            return None
        track = card.track_for(session.direction)
        if not track.is_due(self.clock.now()):
            return None
        return session

    def _activate_session(
        self,
        *,
        session: TelegramQuizSession,
        activate: bool,
        message_id: int | None,
    ) -> TelegramQuizSession:
        if not activate and message_id is None:
            return session
        updated = session
        if activate and session.awaiting_start:
            updated = replace(updated, awaiting_start=False)
        if message_id is not None and updated.message_id != message_id:
            updated = replace(updated, message_id=message_id)
        if updated == session:
            return session
        return self.quiz_session_repository.save(updated)

    def _build_prompt(self, session: TelegramQuizSession):
        card = load_user_card(
            phrase_repository=self.phrase_repository,
            card_id=session.card_id,
            user_id=session.user_id,
        )
        return build_quiz_prompt(
            card=card,
            direction=session.direction,
            session_position=session.answered_prompts + 1,
            total_prompts=session.total_prompts,
        )


@dataclass(slots=True)
class SkipQuizSessionUseCase:
    """Skip the current card and advance the Telegram quiz session."""

    phrase_repository: PhraseRepository
    quiz_session_repository: QuizSessionRepository
    clock: Clock

    def execute(self, user_id: int) -> SkipQuizResult | None:
        session = self.quiz_session_repository.get(user_id)
        if session is None:
            return None
        next_session = self._advance(session)
        if next_session is None:
            self.quiz_session_repository.delete(user_id)
            return SkipQuizResult(
                next_prompt=None,
                session_summary=self._build_summary(session),
            )
        stored_session = self.quiz_session_repository.save(next_session)
        return SkipQuizResult(
            next_prompt=self._build_prompt(stored_session),
            session_summary=None,
        )

    def _advance(
        self, session: TelegramQuizSession
    ) -> TelegramQuizSession | None:
        if not session.pending_reviews:
            return None
        next_item = session.pending_reviews[0]
        return replace(
            session,
            card_id=next_item.card_id,
            direction=next_item.direction,
            pending_reviews=session.pending_reviews[1:],
            awaiting_start=False,
        )

    def _build_prompt(self, session: TelegramQuizSession):
        card = load_user_card(
            phrase_repository=self.phrase_repository,
            card_id=session.card_id,
            user_id=session.user_id,
        )
        return build_quiz_prompt(
            card=card,
            direction=session.direction,
            session_position=session.answered_prompts + 1,
            total_prompts=session.total_prompts,
        )

    def _build_summary(self, session: TelegramQuizSession):
        remaining_due_reviews = len(
            list_due_reviews(
                phrase_repository=self.phrase_repository,
                user_id=session.user_id,
                now=self.clock.now(),
            )
        )
        return build_quiz_summary(
            total_prompts=session.total_prompts,
            answered_prompts=session.answered_prompts,
            correct_prompts=session.correct_prompts,
            incorrect_prompts=session.incorrect_prompts,
            remaining_due_reviews=remaining_due_reviews,
        )


@dataclass(slots=True)
class EndQuizSessionUseCase:
    """Exit the active Telegram quiz session immediately."""

    quiz_session_repository: QuizSessionRepository

    def execute(self, user_id: int) -> bool:
        session = self.quiz_session_repository.get(user_id)
        if session is None:
            return False
        self.quiz_session_repository.delete(user_id)
        return True


@dataclass(slots=True)
class SubmitActiveQuizAnswerUseCase:
    """Submit an answer for the current Telegram quiz session."""

    quiz_session_repository: QuizSessionRepository
    phrase_repository: PhraseRepository
    submit_review_answer_use_case: SubmitReviewAnswerUseCase
    clock: Clock

    def execute(
        self, user_id: int, answer_text: str
    ) -> ActiveQuizAnswerResult:
        session = self.quiz_session_repository.get(user_id)
        if session is None:
            raise QuizSessionNotFoundError("No active quiz session was found.")
        if session.awaiting_start:
            raise QuizSessionNotFoundError("Start the quiz before answering.")
        review_result = self.submit_review_answer_use_case.execute(
            SubmitReviewAnswerCommand(
                user_id=user_id,
                card_id=session.card_id,
                direction=session.direction,
                answer_text=answer_text,
            )
        )
        next_session = self._advance(
            session=session,
            was_correct=review_result.outcome is ReviewOutcome.CORRECT,
        )
        if next_session is None:
            self.quiz_session_repository.delete(user_id)
            return ActiveQuizAnswerResult(
                review_result=review_result,
                next_prompt=None,
                session_summary=self._build_summary(
                    session=session,
                    was_correct=review_result.outcome
                    is ReviewOutcome.CORRECT,
                ),
            )
        stored_session = self.quiz_session_repository.save(next_session)
        return ActiveQuizAnswerResult(
            review_result=review_result,
            next_prompt=self._build_prompt(stored_session),
            session_summary=None,
        )

    def _advance(
        self,
        *,
        session: TelegramQuizSession,
        was_correct: bool,
    ) -> TelegramQuizSession | None:
        if not session.pending_reviews:
            return None
        next_item = session.pending_reviews[0]
        return replace(
            session,
            card_id=next_item.card_id,
            direction=next_item.direction,
            pending_reviews=session.pending_reviews[1:],
            answered_prompts=session.answered_prompts + 1,
            correct_prompts=(
                session.correct_prompts + (1 if was_correct else 0)
            ),
            incorrect_prompts=(
                session.incorrect_prompts + (0 if was_correct else 1)
            ),
            awaiting_start=False,
        )

    def _build_prompt(self, session: TelegramQuizSession):
        card = load_user_card(
            phrase_repository=self.phrase_repository,
            card_id=session.card_id,
            user_id=session.user_id,
        )
        return build_quiz_prompt(
            card=card,
            direction=session.direction,
            session_position=session.answered_prompts + 1,
            total_prompts=session.total_prompts,
        )

    def _build_summary(
        self,
        *,
        session: TelegramQuizSession,
        was_correct: bool,
    ):
        remaining_due_reviews = len(
            list_due_reviews(
                phrase_repository=self.phrase_repository,
                user_id=session.user_id,
                now=self.clock.now(),
            )
        )
        return build_quiz_summary(
            total_prompts=session.total_prompts,
            answered_prompts=session.answered_prompts + 1,
            correct_prompts=(
                session.correct_prompts + (1 if was_correct else 0)
            ),
            incorrect_prompts=(
                session.incorrect_prompts + (0 if was_correct else 1)
            ),
            remaining_due_reviews=remaining_due_reviews,
        )
