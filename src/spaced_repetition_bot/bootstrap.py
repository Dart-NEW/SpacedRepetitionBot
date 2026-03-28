"""Composition root for the application."""

from __future__ import annotations

from dataclasses import dataclass

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
from spaced_repetition_bot.infrastructure.clock import SystemClock
from spaced_repetition_bot.infrastructure.config import AppConfig
from spaced_repetition_bot.infrastructure.repositories import (
    InMemoryPhraseRepository,
    InMemorySettingsRepository,
)
from spaced_repetition_bot.infrastructure.translators import (
    MockTranslationProvider,
)


@dataclass(slots=True)
class ApplicationContainer:
    """All wired application services."""

    config: AppConfig
    translate_phrase: TranslatePhraseUseCase
    get_history: GetHistoryUseCase
    toggle_learning: ToggleLearningUseCase
    get_due_reviews: GetDueReviewsUseCase
    submit_review_answer: SubmitReviewAnswerUseCase
    get_user_progress: GetUserProgressUseCase
    get_settings: GetSettingsUseCase
    update_settings: UpdateSettingsUseCase


def build_container(config: AppConfig | None = None) -> ApplicationContainer:
    """Build the dependency graph for the MVP."""

    app_config = config or AppConfig()
    clock = SystemClock()
    phrase_repository = InMemoryPhraseRepository()
    settings_repository = InMemorySettingsRepository()
    translator = MockTranslationProvider()
    spaced_repetition_policy = FixedIntervalSpacedRepetitionPolicy()
    answer_evaluation_policy = NormalizedTextAnswerPolicy()

    return ApplicationContainer(
        config=app_config,
        translate_phrase=TranslatePhraseUseCase(
            phrase_repository=phrase_repository,
            settings_repository=settings_repository,
            translation_provider=translator,
            spaced_repetition_policy=spaced_repetition_policy,
            clock=clock,
        ),
        get_history=GetHistoryUseCase(phrase_repository=phrase_repository),
        toggle_learning=ToggleLearningUseCase(
            phrase_repository=phrase_repository
        ),
        get_due_reviews=GetDueReviewsUseCase(
            phrase_repository=phrase_repository,
            clock=clock,
        ),
        submit_review_answer=SubmitReviewAnswerUseCase(
            phrase_repository=phrase_repository,
            spaced_repetition_policy=spaced_repetition_policy,
            answer_evaluation_policy=answer_evaluation_policy,
            clock=clock,
        ),
        get_user_progress=GetUserProgressUseCase(
            phrase_repository=phrase_repository,
            clock=clock,
        ),
        get_settings=GetSettingsUseCase(
            settings_repository=settings_repository
        ),
        update_settings=UpdateSettingsUseCase(
            settings_repository=settings_repository
        ),
    )
