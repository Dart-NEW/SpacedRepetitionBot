"""Core tests for the MVP use cases."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from uuid import uuid4

import pytest

from spaced_repetition_bot.application.dtos import (
    GetHistoryQuery,
    GetSettingsQuery,
    GetUserProgressQuery,
    SubmitReviewAnswerCommand,
    ToggleLearningCommand,
    TranslatePhraseCommand,
    UpdateSettingsCommand,
)
from spaced_repetition_bot.application.errors import (
    CardNotFoundError,
    LearningDisabledError,
    ReviewNotAvailableError,
)
from spaced_repetition_bot.application.use_cases import (
    GetHistoryUseCase,
)
from spaced_repetition_bot.domain.enums import (
    LearningStatus,
    ReviewDirection,
    ReviewOutcome,
)

from spaced_repetition_bot.domain.models import UserSettings

from tests.support import build_test_context


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
    assert all(
        item.next_review_at == now + timedelta(days=2)
        for item in result.scheduled_reviews
    )


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


def test_translate_phrase_uses_saved_settings_defaults() -> None:
    now = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
    context = build_test_context(now)
    context["settings_repository"].save(
        UserSettings(
            user_id=7, default_source_lang="es", default_target_lang="en"
        )
    )

    result = context["translate"].execute(
        TranslatePhraseCommand(
            user_id=7,
            text="buena suerte",
        )
    )

    assert result.source_lang == "es"
    assert result.target_lang == "en"
    assert result.translated_text == "good luck"


def test_get_history_returns_newest_first_with_limit() -> None:
    now = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
    context = build_test_context(now)
    history = GetHistoryUseCase(phrase_repository=context["phrase_repository"])

    context["translate"].execute(
        TranslatePhraseCommand(
            user_id=1,
            text="first phrase",
            source_lang="en",
            target_lang="es",
        )
    )
    context["clock"].current = now + timedelta(minutes=5)
    context["translate"].execute(
        TranslatePhraseCommand(
            user_id=1,
            text="second phrase",
            source_lang="en",
            target_lang="es",
        )
    )

    result = history.execute(GetHistoryQuery(user_id=1, limit=1))

    assert len(result) == 1
    assert result[0].source_text == "second phrase"


def test_toggle_learning_raises_for_unknown_card() -> None:
    now = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
    context = build_test_context(now)

    with pytest.raises(CardNotFoundError):
        context["toggle"].execute(
            ToggleLearningCommand(
                user_id=1,
                card_id=uuid4(),
                learning_enabled=False,
            )
        )


def test_due_reviews_ignore_tracks_before_due_date() -> None:
    now = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
    context = build_test_context(now)
    context["translate"].execute(
        TranslatePhraseCommand(
            user_id=1,
            text="good luck",
            source_lang="en",
            target_lang="es",
        )
    )
    context["clock"].current = now + timedelta(days=1)

    due_reviews = context["due"].execute(user_id=1)

    assert due_reviews == []


def test_submit_review_answer_raises_when_learning_is_disabled() -> None:
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

    with pytest.raises(LearningDisabledError):
        context["answer"].execute(
            SubmitReviewAnswerCommand(
                user_id=1,
                card_id=translate_result.card_id,
                direction=ReviewDirection.FORWARD,
                answer_text="buena suerte",
            )
        )


def test_submit_review_answer_raises_when_review_is_not_due() -> None:
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

    with pytest.raises(ReviewNotAvailableError):
        context["answer"].execute(
            SubmitReviewAnswerCommand(
                user_id=1,
                card_id=translate_result.card_id,
                direction=ReviewDirection.FORWARD,
                answer_text="buena suerte",
            )
        )


def test_submit_review_answer_raises_for_missing_card() -> None:
    now = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
    context = build_test_context(now)

    with pytest.raises(CardNotFoundError):
        context["answer"].execute(
            SubmitReviewAnswerCommand(
                user_id=1,
                card_id=uuid4(),
                direction=ReviewDirection.FORWARD,
                answer_text="buena suerte",
            )
        )


def test_settings_use_cases_return_defaults_and_persist_updates() -> None:
    now = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
    context = build_test_context(now)

    default_settings = context["get_settings"].execute(
        GetSettingsQuery(user_id=33)
    )
    assert default_settings.default_source_lang == "en"
    assert default_settings.default_target_lang == "es"
    assert default_settings.timezone == "UTC"

    updated_settings = context["update_settings"].execute(
        UpdateSettingsCommand(
            user_id=33,
            default_source_lang="de",
            default_target_lang="it",
            timezone="Europe/Berlin",
            notification_time_local=time(hour=7, minute=30),
            notifications_enabled=False,
        )
    )

    stored_settings = context["get_settings"].execute(
        GetSettingsQuery(user_id=33)
    )

    assert updated_settings == stored_settings
    assert stored_settings.default_source_lang == "de"
    assert stored_settings.default_target_lang == "it"
    assert stored_settings.timezone == "Europe/Berlin"
    assert stored_settings.notification_time_local == time(hour=7, minute=30)
    assert stored_settings.notifications_enabled is False
