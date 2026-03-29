"""Shared test helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from spaced_repetition_bot.application.use_cases import (
    GetDueReviewsUseCase,
    GetHistoryUseCase,
    GetSettingsUseCase,
    GetUserProgressUseCase,
    SkipQuizSessionUseCase,
    StartQuizSessionUseCase,
    SubmitActiveQuizAnswerUseCase,
    SubmitReviewAnswerUseCase,
    ToggleLearningUseCase,
    TranslatePhraseUseCase,
    UpdateSettingsUseCase,
)
from spaced_repetition_bot.domain.policies import (
    FixedIntervalSpacedRepetitionPolicy,
    NormalizedTextAnswerPolicy,
)
from spaced_repetition_bot.infrastructure.repositories import (
    InMemoryPhraseRepository,
    InMemoryQuizSessionRepository,
    InMemorySettingsRepository,
)
from spaced_repetition_bot.infrastructure.translators import (
    MockTranslationProvider,
)


DEFAULT_GLOSSARY = {
    ("good luck", "en", "es"): "buena suerte",
    ("buena suerte", "es", "en"): "good luck",
}


@dataclass(slots=True)
class FixedClock:
    """Deterministic clock for tests."""

    current: datetime

    def now(self) -> datetime:
        return self.current


@dataclass(slots=True)
class NoOpReminderService:
    """Minimal reminder service stub for container wiring tests."""

    async def run(self, bot: object) -> None:
        return None


def build_test_dependencies(now: datetime) -> dict[str, object]:
    """Build raw dependency objects used across tests."""

    return {
        "phrase_repository": InMemoryPhraseRepository(),
        "settings_repository": InMemorySettingsRepository(),
        "quiz_session_repository": InMemoryQuizSessionRepository(),
        "translator": MockTranslationProvider(
            glossary=DEFAULT_GLOSSARY.copy()
        ),
        "clock": FixedClock(current=now),
        "scheduler": FixedIntervalSpacedRepetitionPolicy(),
        "answer_policy": NormalizedTextAnswerPolicy(),
    }


def build_test_use_cases(dependencies: dict[str, object]) -> dict[str, object]:
    """Wire test dependencies into application use cases."""

    phrase_repository = dependencies["phrase_repository"]
    settings_repository = dependencies["settings_repository"]
    quiz_session_repository = dependencies["quiz_session_repository"]
    translator = dependencies["translator"]
    clock = dependencies["clock"]
    scheduler = dependencies["scheduler"]
    answer_policy = dependencies["answer_policy"]
    start_quiz_session = StartQuizSessionUseCase(
        phrase_repository=phrase_repository,
        quiz_session_repository=quiz_session_repository,
        clock=clock,
    )
    submit_review_answer = SubmitReviewAnswerUseCase(
        phrase_repository=phrase_repository,
        spaced_repetition_policy=scheduler,
        answer_evaluation_policy=answer_policy,
        clock=clock,
    )

    return {
        "translate": TranslatePhraseUseCase(
            phrase_repository=phrase_repository,
            settings_repository=settings_repository,
            translation_provider=translator,
            spaced_repetition_policy=scheduler,
            clock=clock,
        ),
        "get_history": GetHistoryUseCase(phrase_repository=phrase_repository),
        "answer": submit_review_answer,
        "due": GetDueReviewsUseCase(
            phrase_repository=phrase_repository,
            clock=clock,
        ),
        "toggle": ToggleLearningUseCase(phrase_repository=phrase_repository),
        "progress": GetUserProgressUseCase(
            phrase_repository=phrase_repository,
            clock=clock,
        ),
        "get_settings": GetSettingsUseCase(
            settings_repository=settings_repository
        ),
        "update_settings": UpdateSettingsUseCase(
            settings_repository=settings_repository
        ),
        "start_quiz": start_quiz_session,
        "skip_quiz": SkipQuizSessionUseCase(
            quiz_session_repository=quiz_session_repository,
        ),
        "submit_active_quiz": SubmitActiveQuizAnswerUseCase(
            quiz_session_repository=quiz_session_repository,
            submit_review_answer_use_case=submit_review_answer,
            start_quiz_session_use_case=start_quiz_session,
        ),
    }


def build_test_context(now: datetime) -> dict[str, object]:
    """Build a complete test context with dependencies and use cases."""

    dependencies = build_test_dependencies(now)
    use_cases = build_test_use_cases(dependencies)
    return {**dependencies, **use_cases}
