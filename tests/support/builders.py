"""Factory helpers for test setup."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import FastAPI

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
from spaced_repetition_bot.bootstrap import ApplicationContainer
from spaced_repetition_bot.domain.enums import LearningStatus, ReviewDirection
from spaced_repetition_bot.domain.models import PhraseCard, ReviewTrack
from spaced_repetition_bot.domain.policies import (
    FixedIntervalSpacedRepetitionPolicy,
    NormalizedTextAnswerPolicy,
)
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
    InMemoryPhraseRepository,
    InMemoryQuizSessionRepository,
    InMemorySettingsRepository,
)
from spaced_repetition_bot.infrastructure.translators import (
    MockTranslationProvider,
)
from spaced_repetition_bot.presentation.api import build_api_router

DEFAULT_GLOSSARY = {
    ("good luck", "en", "es"): "buena suerte",
    ("buena suerte", "es", "en"): "good luck",
    ("hello", "en", "es"): "hola",
    ("hola", "es", "en"): "hello",
}


@dataclass(slots=True)
class FixedClock:
    """Deterministic clock for tests."""

    current: datetime

    def now(self) -> datetime:
        return self.current


def build_test_dependencies(now: datetime) -> dict[str, object]:
    """Build the shared dependency set for runtime tests."""

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
    """Wire the canonical application use cases."""

    phrase_repository = dependencies["phrase_repository"]
    settings_repository = dependencies["settings_repository"]
    quiz_session_repository = dependencies["quiz_session_repository"]
    translator = dependencies["translator"]
    clock = dependencies["clock"]
    scheduler = dependencies["scheduler"]
    answer_policy = dependencies["answer_policy"]

    submit_review_answer = SubmitReviewAnswerUseCase(
        phrase_repository=phrase_repository,
        spaced_repetition_policy=scheduler,
        answer_evaluation_policy=answer_policy,
        clock=clock,
    )
    start_quiz_session = StartQuizSessionUseCase(
        phrase_repository=phrase_repository,
        quiz_session_repository=quiz_session_repository,
        clock=clock,
    )

    return {
        "translate_phrase": TranslatePhraseUseCase(
            phrase_repository=phrase_repository,
            settings_repository=settings_repository,
            translation_provider=translator,
            spaced_repetition_policy=scheduler,
            clock=clock,
        ),
        "get_history": GetHistoryUseCase(phrase_repository=phrase_repository),
        "toggle_learning": ToggleLearningUseCase(
            phrase_repository=phrase_repository
        ),
        "get_due_reviews": GetDueReviewsUseCase(
            phrase_repository=phrase_repository,
            clock=clock,
        ),
        "start_quiz_session": start_quiz_session,
        "skip_quiz_session": SkipQuizSessionUseCase(
            quiz_session_repository=quiz_session_repository
        ),
        "submit_active_quiz_answer": SubmitActiveQuizAnswerUseCase(
            quiz_session_repository=quiz_session_repository,
            submit_review_answer_use_case=submit_review_answer,
            start_quiz_session_use_case=start_quiz_session,
        ),
        "submit_review_answer": submit_review_answer,
        "get_user_progress": GetUserProgressUseCase(
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


def build_test_container(now: datetime) -> ApplicationContainer:
    """Build a fully wired application container for tests."""

    dependencies = build_test_dependencies(now)
    use_cases = build_test_use_cases(dependencies)
    config = AppConfig(
        app_name="Test App",
        app_version="9.9.9",
        api_prefix="/api/test",
        telegram_bot_token="test-token",
        reminder_poll_interval_seconds=0,
    )
    reminder_service = TelegramReminderService(
        settings_repository=dependencies["settings_repository"],
        get_due_reviews_use_case=use_cases["get_due_reviews"],
        clock=dependencies["clock"],
        poll_interval_seconds=0,
    )
    return ApplicationContainer(
        config=config,
        translate_phrase=use_cases["translate_phrase"],
        get_history=use_cases["get_history"],
        toggle_learning=use_cases["toggle_learning"],
        get_due_reviews=use_cases["get_due_reviews"],
        start_quiz_session=use_cases["start_quiz_session"],
        skip_quiz_session=use_cases["skip_quiz_session"],
        submit_active_quiz_answer=use_cases["submit_active_quiz_answer"],
        submit_review_answer=use_cases["submit_review_answer"],
        get_user_progress=use_cases["get_user_progress"],
        get_settings=use_cases["get_settings"],
        update_settings=use_cases["update_settings"],
        settings_repository=dependencies["settings_repository"],
        clock=dependencies["clock"],
        reminder_service=reminder_service,
    )


def build_api_test_app(container: ApplicationContainer) -> FastAPI:
    """Build a FastAPI test application bound to a container."""

    app = FastAPI(
        title=container.config.app_name,
        version=container.config.app_version,
        description="Test application",
    )
    app.include_router(
        build_api_router(container),
        prefix=container.config.api_prefix,
    )
    return app


def build_session_factory_for_tests(database_url: str = "sqlite:///:memory:"):
    """Build an initialized SQLAlchemy session factory."""

    engine = build_engine(database_url)
    initialize_database(engine)
    session_factory = build_session_factory(engine)
    session_factory._test_engine = engine
    return session_factory


def create_card(
    now: datetime,
    *,
    user_id: int = 1,
    source_text: str = "good luck",
    target_text: str = "buena suerte",
    source_lang: str = "en",
    target_lang: str = "es",
    learning_status: LearningStatus = LearningStatus.ACTIVE,
    forward_step_index: int = 0,
    reverse_step_index: int = 0,
    forward_due_in_days: int | None = 2,
    reverse_due_in_days: int | None = 2,
    forward_completed: bool = False,
    reverse_completed: bool = False,
    archived_reason: str | None = None,
) -> PhraseCard:
    """Create a phrase card with configurable track state."""

    forward_completed_at = now if forward_completed else None
    reverse_completed_at = now if reverse_completed else None
    return PhraseCard(
        id=uuid4(),
        user_id=user_id,
        source_text=source_text,
        target_text=target_text,
        source_lang=source_lang,
        target_lang=target_lang,
        created_at=now,
        learning_status=learning_status,
        review_tracks=(
            ReviewTrack(
                direction=ReviewDirection.FORWARD,
                step_index=forward_step_index,
                next_review_at=(
                    None
                    if forward_due_in_days is None
                    else now + timedelta(days=forward_due_in_days)
                ),
                completed_at=forward_completed_at,
            ),
            ReviewTrack(
                direction=ReviewDirection.REVERSE,
                step_index=reverse_step_index,
                next_review_at=(
                    None
                    if reverse_due_in_days is None
                    else now + timedelta(days=reverse_due_in_days)
                ),
                completed_at=reverse_completed_at,
            ),
        ),
        archived_reason=archived_reason,
    )
