"""Core tests for the MVP use cases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from spaced_repetition_bot.application.dtos import (
    GetUserProgressQuery,
    SubmitReviewAnswerCommand,
    ToggleLearningCommand,
    TranslatePhraseCommand,
)
from spaced_repetition_bot.application.use_cases import (
    GetDueReviewsUseCase,
    GetUserProgressUseCase,
    SubmitReviewAnswerUseCase,
    ToggleLearningUseCase,
    TranslatePhraseUseCase,
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
    InMemorySettingsRepository,
)
from spaced_repetition_bot.infrastructure.translators import MockTranslationProvider


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
    translator = MockTranslationProvider(
        glossary={
            ("good luck", "en", "es"): "buena suerte",
            ("buena suerte", "es", "en"): "good luck",
        }
    )
    clock = FixedClock(current=now)
    scheduler = FixedIntervalSpacedRepetitionPolicy()

    return {
        "clock": clock,
        "translate": TranslatePhraseUseCase(
            phrase_repository=phrase_repository,
            settings_repository=settings_repository,
            translation_provider=translator,
            spaced_repetition_policy=scheduler,
            clock=clock,
        ),
        "answer": SubmitReviewAnswerUseCase(
            phrase_repository=phrase_repository,
            spaced_repetition_policy=scheduler,
            answer_evaluation_policy=NormalizedTextAnswerPolicy(),
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
    }


def test_translate_phrase_creates_two_review_tracks() -> None:
    now = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
    context = build_test_context(now)

    result = context["translate"].execute(
        TranslatePhraseCommand(
            user_id=1,
            text="good luck",
            source_lang="en",
            target_lang="es",
        )
    )

    assert result.translated_text == "buena suerte"
    assert result.learning_status is LearningStatus.ACTIVE
    assert len(result.scheduled_reviews) == 2
    assert all(item.next_review_at == now + timedelta(days=2) for item in result.scheduled_reviews)


def test_correct_answer_advances_next_interval() -> None:
    now = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
    context = build_test_context(now)
    translate_result = context["translate"].execute(
        TranslatePhraseCommand(
            user_id=1,
            text="good luck",
            source_lang="en",
            target_lang="es",
        )
    )
    context["clock"].current = now + timedelta(days=2)

    review_result = context["answer"].execute(
        SubmitReviewAnswerCommand(
            user_id=1,
            card_id=translate_result.card_id,
            direction=ReviewDirection.FORWARD,
            answer_text=" BUENA SUERTE ",
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
            source_lang="en",
            target_lang="es",
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
            source_lang="en",
            target_lang="es",
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
            source_lang="en",
            target_lang="es",
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
