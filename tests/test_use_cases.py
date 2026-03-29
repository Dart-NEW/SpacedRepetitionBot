"""Core tests for the MVP use cases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from spaced_repetition_bot.application.dtos import (
    GetUserProgressQuery,
    SubmitReviewAnswerCommand,
    ToggleLearningCommand,
    TranslatePhraseCommand,
    UpdateSettingsCommand,
)
from spaced_repetition_bot.application.use_cases import (
    GetDueReviewsUseCase,
    GetUserProgressUseCase,
    SkipQuizSessionUseCase,
    StartQuizSessionUseCase,
    SubmitActiveQuizAnswerUseCase,
    SubmitReviewAnswerUseCase,
    ToggleLearningUseCase,
    TranslatePhraseUseCase,
    UpdateSettingsUseCase,
)
from spaced_repetition_bot.domain.enums import (
    LearningStatus,
    ReviewDirection,
    ReviewOutcome,
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


@dataclass(slots=True)
class FixedClock:
    """Deterministic clock for tests."""

    current: datetime

    def now(self) -> datetime:
        return self.current


def build_test_context(now: datetime) -> dict[str, object]:
    """Build wired test dependencies."""

    phrase_repository = InMemoryPhraseRepository()
    settings_repository = InMemorySettingsRepository()
    quiz_session_repository = InMemoryQuizSessionRepository()
    translator = MockTranslationProvider(
        glossary={
            ("good luck", "en", "es"): "buena suerte",
            ("buena suerte", "es", "en"): "good luck",
        }
    )
    clock = FixedClock(current=now)
    scheduler = FixedIntervalSpacedRepetitionPolicy()
    submit_review_answer = SubmitReviewAnswerUseCase(
        phrase_repository=phrase_repository,
        spaced_repetition_policy=scheduler,
        answer_evaluation_policy=NormalizedTextAnswerPolicy(),
        clock=clock,
    )
    start_quiz_session = StartQuizSessionUseCase(
        phrase_repository=phrase_repository,
        quiz_session_repository=quiz_session_repository,
        clock=clock,
    )

    return {
        "clock": clock,
        "phrase_repository": phrase_repository,
        "settings_repository": settings_repository,
        "translate": TranslatePhraseUseCase(
            phrase_repository=phrase_repository,
            settings_repository=settings_repository,
            translation_provider=translator,
            spaced_repetition_policy=scheduler,
            clock=clock,
        ),
        "update_settings": UpdateSettingsUseCase(
            settings_repository=settings_repository,
        ),
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


def build_test_context_with_scheduler(
    now: datetime,
    scheduler: FixedIntervalSpacedRepetitionPolicy,
) -> dict[str, object]:
    """Build wired test dependencies with a custom review scheduler."""

    phrase_repository = InMemoryPhraseRepository()
    settings_repository = InMemorySettingsRepository()
    quiz_session_repository = InMemoryQuizSessionRepository()
    translator = MockTranslationProvider(
        glossary={
            ("good luck", "en", "es"): "buena suerte",
            ("buena suerte", "es", "en"): "good luck",
        }
    )
    clock = FixedClock(current=now)
    submit_review_answer = SubmitReviewAnswerUseCase(
        phrase_repository=phrase_repository,
        spaced_repetition_policy=scheduler,
        answer_evaluation_policy=NormalizedTextAnswerPolicy(),
        clock=clock,
    )
    start_quiz_session = StartQuizSessionUseCase(
        phrase_repository=phrase_repository,
        quiz_session_repository=quiz_session_repository,
        clock=clock,
    )

    return {
        "clock": clock,
        "phrase_repository": phrase_repository,
        "settings_repository": settings_repository,
        "translate": TranslatePhraseUseCase(
            phrase_repository=phrase_repository,
            settings_repository=settings_repository,
            translation_provider=translator,
            spaced_repetition_policy=scheduler,
            clock=clock,
        ),
        "update_settings": UpdateSettingsUseCase(
            settings_repository=settings_repository,
        ),
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


def test_translate_phrase_creates_two_review_tracks() -> None:
    now = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
    context = build_test_context(now)

    result = context["translate"].execute(
        TranslatePhraseCommand(
            user_id=1,
            text="good luck",
        )
    )

    assert result.translated_text == "buena suerte"
    assert result.direction is ReviewDirection.FORWARD
    assert result.learning_status is LearningStatus.ACTIVE
    assert len(result.scheduled_reviews) == 2
    assert all(
        item.next_review_at == now + timedelta(days=2)
        for item in result.scheduled_reviews
    )


def test_translate_phrase_supports_minute_based_review_schedule() -> None:
    now = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
    context = build_test_context_with_scheduler(
        now,
        FixedIntervalSpacedRepetitionPolicy(
            intervals=(2, 3, 5, 7),
            interval_unit="minutes",
        ),
    )

    result = context["translate"].execute(
        TranslatePhraseCommand(
            user_id=1,
            text="good luck",
        )
    )

    assert all(
        item.next_review_at == now + timedelta(minutes=2)
        for item in result.scheduled_reviews
    )


def test_translate_uses_reverse_direction_from_settings() -> None:
    now = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
    context = build_test_context(now)
    context["update_settings"].execute(
        UpdateSettingsCommand(
            user_id=1,
            default_source_lang="en",
            default_target_lang="es",
            default_translation_direction=ReviewDirection.REVERSE,
            timezone="UTC",
            notification_time_local=now.timetz().replace(tzinfo=None),
            notifications_enabled=True,
        )
    )

    result = context["translate"].execute(
        TranslatePhraseCommand(
            user_id=1,
            text="buena suerte",
        )
    )

    assert result.direction is ReviewDirection.REVERSE
    assert result.source_lang == "es"
    assert result.target_lang == "en"
    assert result.translated_text == "good luck"


def test_correct_answer_advances_next_interval() -> None:
    now = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
    context = build_test_context(now)
    translate_result = context["translate"].execute(
        TranslatePhraseCommand(
            user_id=1,
            text="good luck",
        )
    )
    context["clock"].current = now + timedelta(days=2)

    review_result = context["answer"].execute(
        SubmitReviewAnswerCommand(
            user_id=1,
            card_id=translate_result.card_id,
            direction=ReviewDirection.FORWARD,
            answer_text=" BUENA-SUERTE ",
        )
    )

    assert review_result.outcome is ReviewOutcome.CORRECT
    assert review_result.step_index == 1
    assert review_result.next_review_at == now + timedelta(days=5)


def test_incorrect_answer_resets_progress() -> None:
    now = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
    context = build_test_context(now)
    translate_result = context["translate"].execute(
        TranslatePhraseCommand(
            user_id=1,
            text="good luck",
        )
    )
    context["clock"].current = now + timedelta(days=2)

    review_result = context["answer"].execute(
        SubmitReviewAnswerCommand(
            user_id=1,
            card_id=translate_result.card_id,
            direction=ReviewDirection.FORWARD,
            answer_text="wrong answer",
        )
    )

    assert review_result.outcome is ReviewOutcome.INCORRECT
    assert review_result.step_index == 0
    assert review_result.next_review_at == now + timedelta(days=4)


def test_disabled_card_is_removed_from_due_queue() -> None:
    now = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
    context = build_test_context(now)
    translate_result = context["translate"].execute(
        TranslatePhraseCommand(
            user_id=1,
            text="good luck",
        )
    )
    context["toggle"].execute(
        ToggleLearningCommand(
            user_id=1,
            card_id=translate_result.card_id,
            learning_enabled=False,
        )
    )
    context["clock"].current = now + timedelta(days=2)

    due_reviews = context["due"].execute(user_id=1)

    assert due_reviews == []


def test_progress_counts_disabled_cards_and_due_reviews() -> None:
    now = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
    context = build_test_context(now)
    translate_result = context["translate"].execute(
        TranslatePhraseCommand(
            user_id=1,
            text="good luck",
        )
    )
    context["toggle"].execute(
        ToggleLearningCommand(
            user_id=1,
            card_id=translate_result.card_id,
            learning_enabled=False,
        )
    )

    progress = context["progress"].execute(GetUserProgressQuery(user_id=1))

    assert progress.total_cards == 1
    assert progress.active_cards == 0
    assert progress.not_learning_cards == 1
    assert progress.due_reviews == 0


def test_quiz_session_resumes_and_moves_to_next_due_prompt() -> None:
    now = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
    context = build_test_context(now)
    translate_result = context["translate"].execute(
        TranslatePhraseCommand(user_id=1, text="good luck")
    )
    context["clock"].current = now + timedelta(days=2)

    first_prompt = context["start_quiz"].execute(user_id=1)
    quiz_result = context["submit_active_quiz"].execute(
        user_id=1,
        answer_text="buena suerte",
    )

    assert first_prompt is not None
    assert first_prompt.card_id == translate_result.card_id
    assert quiz_result.review_result.outcome is ReviewOutcome.CORRECT
    assert quiz_result.next_prompt is not None
    assert quiz_result.next_prompt.direction is ReviewDirection.REVERSE


def test_skip_quiz_session_keeps_reviews_due() -> None:
    now = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
    context = build_test_context(now)
    context["translate"].execute(
        TranslatePhraseCommand(user_id=1, text="good luck")
    )
    context["clock"].current = now + timedelta(days=2)

    prompt = context["start_quiz"].execute(user_id=1)
    skipped = context["skip_quiz"].execute(user_id=1)
    due_reviews = context["due"].execute(user_id=1)

    assert prompt is not None
    assert skipped is True
    assert len(due_reviews) == 2
