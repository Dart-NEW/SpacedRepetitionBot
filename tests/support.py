"""Shared test helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from spaced_repetition_bot.application.use_cases import (
    GetDueReviewsUseCase,
    GetHistoryUseCase,
    GetSettingsUseCase,
    GetUserProgressUseCase,
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


def build_test_dependencies(now: datetime) -> dict[str, object]:
    """Build raw dependency objects used across tests."""

    return {
        "phrase_repository": InMemoryPhraseRepository(),
        "settings_repository": InMemorySettingsRepository(),
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
    translator = dependencies["translator"]
    clock = dependencies["clock"]
    scheduler = dependencies["scheduler"]
    answer_policy = dependencies["answer_policy"]

    return {
        "translate": TranslatePhraseUseCase(
            phrase_repository=phrase_repository,
            settings_repository=settings_repository,
            translation_provider=translator,
            spaced_repetition_policy=scheduler,
            clock=clock,
        ),
        "get_history": GetHistoryUseCase(phrase_repository=phrase_repository),
        "answer": SubmitReviewAnswerUseCase(
            phrase_repository=phrase_repository,
            spaced_repetition_policy=scheduler,
            answer_evaluation_policy=answer_policy,
            clock=clock,
        ),
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
    }


def build_test_context(now: datetime) -> dict[str, object]:
    """Build a complete test context with dependencies and use cases."""

    dependencies = build_test_dependencies(now)
    use_cases = build_test_use_cases(dependencies)
    return {**dependencies, **use_cases}
