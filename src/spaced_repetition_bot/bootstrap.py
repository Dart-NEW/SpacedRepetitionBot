"""Composition root for the application."""

from __future__ import annotations

from dataclasses import dataclass

from spaced_repetition_bot.application.ports import TranslationProvider
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
from spaced_repetition_bot.infrastructure.clock import SystemClock
from spaced_repetition_bot.infrastructure.config import AppConfig
from spaced_repetition_bot.infrastructure.database import (
    build_engine,
    build_session_factory,
    initialize_database,
)
from spaced_repetition_bot.infrastructure.reminders import (
    TelegramReminderService,
)
from spaced_repetition_bot.infrastructure.repositories import (
    SqlAlchemyPhraseRepository,
    SqlAlchemyQuizSessionRepository,
    SqlAlchemySettingsRepository,
)
from spaced_repetition_bot.infrastructure.translators import (
    MockTranslationProvider,
    YandexTranslationProvider,
)


@dataclass(slots=True)
class ApplicationContainer:
    """All wired application services."""

    config: AppConfig
    translate_phrase: TranslatePhraseUseCase
    get_history: GetHistoryUseCase
    toggle_learning: ToggleLearningUseCase
    get_due_reviews: GetDueReviewsUseCase
    start_quiz_session: StartQuizSessionUseCase
    skip_quiz_session: SkipQuizSessionUseCase
    submit_active_quiz_answer: SubmitActiveQuizAnswerUseCase
    submit_review_answer: SubmitReviewAnswerUseCase
    get_user_progress: GetUserProgressUseCase
    get_settings: GetSettingsUseCase
    update_settings: UpdateSettingsUseCase
    settings_repository: SqlAlchemySettingsRepository
    clock: SystemClock
    reminder_service: TelegramReminderService


def build_container(config: AppConfig | None = None) -> ApplicationContainer:
    """Build the dependency graph for the MVP."""

    app_config = config or AppConfig()
    clock = SystemClock()
    engine = build_engine(app_config.database_url)
    initialize_database(engine)
    session_factory = build_session_factory(engine)
    phrase_repository = SqlAlchemyPhraseRepository(
        session_factory=session_factory
    )
    settings_repository = SqlAlchemySettingsRepository(
        session_factory=session_factory
    )
    quiz_session_repository = SqlAlchemyQuizSessionRepository(
        session_factory=session_factory
    )
    translator = build_translation_provider(app_config)
    spaced_repetition_policy = FixedIntervalSpacedRepetitionPolicy()
    answer_evaluation_policy = NormalizedTextAnswerPolicy()
    submit_review_answer = SubmitReviewAnswerUseCase(
        phrase_repository=phrase_repository,
        spaced_repetition_policy=spaced_repetition_policy,
        answer_evaluation_policy=answer_evaluation_policy,
        clock=clock,
    )
    start_quiz_session = StartQuizSessionUseCase(
        phrase_repository=phrase_repository,
        quiz_session_repository=quiz_session_repository,
        clock=clock,
    )

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
        start_quiz_session=start_quiz_session,
        skip_quiz_session=SkipQuizSessionUseCase(
            quiz_session_repository=quiz_session_repository,
        ),
        submit_active_quiz_answer=SubmitActiveQuizAnswerUseCase(
            quiz_session_repository=quiz_session_repository,
            submit_review_answer_use_case=submit_review_answer,
            start_quiz_session_use_case=start_quiz_session,
        ),
        submit_review_answer=submit_review_answer,
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
        settings_repository=settings_repository,
        clock=clock,
        reminder_service=TelegramReminderService(
            settings_repository=settings_repository,
            get_due_reviews_use_case=GetDueReviewsUseCase(
                phrase_repository=phrase_repository,
                clock=clock,
            ),
            clock=clock,
            poll_interval_seconds=app_config.reminder_poll_interval_seconds,
        ),
    )


def build_translation_provider(config: AppConfig) -> TranslationProvider:
    """Build the configured translation provider."""

    if config.translation_provider == "mock":
        return MockTranslationProvider()
    if not config.yandex_translate_api_key:
        raise ValueError(
            "SRB_YANDEX_TRANSLATE_API_KEY must be set when "
            "SRB_TRANSLATION_PROVIDER=yandex."
        )
    if not config.yandex_folder_id:
        raise ValueError(
            "SRB_YANDEX_FOLDER_ID must be set when "
            "SRB_TRANSLATION_PROVIDER=yandex."
        )
    return YandexTranslationProvider(
        api_key=config.yandex_translate_api_key,
        folder_id=config.yandex_folder_id,
        endpoint_url=config.yandex_translate_url,
        timeout_seconds=config.translation_timeout_seconds,
    )
