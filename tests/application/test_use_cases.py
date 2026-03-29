"""Application use case tests for the canonical runtime module."""

from __future__ import annotations

from datetime import date, time, timedelta
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
    InvalidSettingsError,
    LearningDisabledError,
    QuizSessionNotFoundError,
    ReviewNotAvailableError,
)
from spaced_repetition_bot.application.use_cases import (
    default_settings,
    load_user_card,
    map_scheduled_review,
    map_settings_snapshot,
)
from spaced_repetition_bot.domain.enums import (
    LearningStatus,
    ReviewDirection,
    ReviewOutcome,
)
from spaced_repetition_bot.domain.models import TelegramQuizSession
from tests.support import create_card

pytestmark = pytest.mark.unit


def test_default_settings_and_snapshot_helpers() -> None:
    settings = default_settings(user_id=42)
    snapshot = map_settings_snapshot(settings)

    assert settings.default_translation_direction is ReviewDirection.FORWARD
    assert snapshot.user_id == 42
    assert snapshot.default_source_lang == "en"
    assert snapshot.default_target_lang == "es"


def test_map_scheduled_review_reflects_track_completion(fixed_now) -> None:
    card = create_card(
        fixed_now,
        forward_due_in_days=None,
        forward_completed=True,
    )

    item = map_scheduled_review(card.review_tracks[0])

    assert item.direction is ReviewDirection.FORWARD
    assert item.completed is True
    assert item.next_review_at is None


def test_translate_phrase_uses_default_settings_when_user_has_no_profile(
    test_use_cases,
) -> None:
    result = test_use_cases["translate_phrase"].execute(
        TranslatePhraseCommand(user_id=1, text="good luck")
    )

    assert result.translated_text == "buena suerte"
    assert result.direction is ReviewDirection.FORWARD
    assert result.source_lang == "en"
    assert result.target_lang == "es"
    assert len(result.scheduled_reviews) == 2


def test_translate_phrase_respects_reverse_direction_and_learn_false(
    test_use_cases,
) -> None:
    test_use_cases["update_settings"].execute(
        UpdateSettingsCommand(
            user_id=1,
            default_source_lang="en",
            default_target_lang="es",
            default_translation_direction=ReviewDirection.REVERSE,
            timezone="UTC",
            notification_time_local=time(hour=9),
            notifications_enabled=True,
        )
    )

    result = test_use_cases["translate_phrase"].execute(
        TranslatePhraseCommand(
            user_id=1,
            text="buena suerte",
            learn=False,
        )
    )
    stored = test_use_cases["get_history"].phrase_repository.get(
        result.card_id
    )

    assert result.direction is ReviewDirection.REVERSE
    assert result.source_lang == "es"
    assert result.target_lang == "en"
    assert result.learning_status is LearningStatus.NOT_LEARNING
    assert stored.archived_reason == "created_without_learning"


def test_get_history_sorts_descending_and_honors_limit(
    test_use_cases,
    fixed_clock,
) -> None:
    test_use_cases["translate_phrase"].execute(
        TranslatePhraseCommand(user_id=1, text="good luck")
    )
    fixed_clock.current += timedelta(minutes=1)
    test_use_cases["translate_phrase"].execute(
        TranslatePhraseCommand(user_id=1, text="hello")
    )

    history = test_use_cases["get_history"].execute(
        GetHistoryQuery(user_id=1, limit=1)
    )

    assert len(history) == 1
    assert history[0].source_text == "hello"


def test_load_user_card_raises_for_missing_or_foreign_card(
    test_dependencies,
    fixed_now,
) -> None:
    card = create_card(fixed_now, user_id=2)
    test_dependencies["phrase_repository"].add(card)

    with pytest.raises(CardNotFoundError):
        load_user_card(
            test_dependencies["phrase_repository"],
            card.id,
            user_id=1,
        )

    with pytest.raises(CardNotFoundError):
        load_user_card(
            test_dependencies["phrase_repository"],
            uuid4(),
            user_id=1,
        )


def test_get_due_reviews_returns_only_active_cards_sorted_by_due_at(
    test_dependencies,
    test_use_cases,
    fixed_clock,
    fixed_now,
) -> None:
    due_late = create_card(
        fixed_now,
        source_text="late",
        target_text="tarde",
        forward_due_in_days=0,
        reverse_due_in_days=5,
    )
    due_early = create_card(
        fixed_now - timedelta(hours=1),
        source_text="early",
        target_text="temprano",
        forward_due_in_days=0,
        reverse_due_in_days=3,
    )
    disabled = create_card(
        fixed_now,
        learning_status=LearningStatus.NOT_LEARNING,
        source_text="disabled",
        target_text="desactivado",
        forward_due_in_days=0,
        reverse_due_in_days=0,
    )
    repository = test_dependencies["phrase_repository"]
    repository.add(due_late)
    repository.add(due_early)
    repository.add(disabled)
    fixed_clock.current = fixed_now

    due_reviews = test_use_cases["get_due_reviews"].execute(user_id=1)

    assert [item.prompt_text for item in due_reviews] == ["early", "late"]


def test_submit_review_answer_handles_correct_incorrect_and_completed_flow(
    test_use_cases,
    fixed_clock,
    fixed_now,
) -> None:
    result = test_use_cases["translate_phrase"].execute(
        TranslatePhraseCommand(user_id=1, text="good luck")
    )
    fixed_clock.current = fixed_now + timedelta(days=2)

    correct = test_use_cases["submit_review_answer"].execute(
        SubmitReviewAnswerCommand(
            user_id=1,
            card_id=result.card_id,
            direction=ReviewDirection.FORWARD,
            answer_text="BUENA-SUERTE",
        )
    )
    incorrect = test_use_cases["submit_review_answer"].execute(
        SubmitReviewAnswerCommand(
            user_id=1,
            card_id=result.card_id,
            direction=ReviewDirection.REVERSE,
            answer_text="wrong answer",
        )
    )

    assert correct.outcome is ReviewOutcome.CORRECT
    assert correct.step_index == 1
    assert incorrect.outcome is ReviewOutcome.INCORRECT
    assert incorrect.step_index == 0


def test_submit_review_answer_marks_card_learned_when_both_tracks_complete(
    test_dependencies,
    test_use_cases,
    fixed_clock,
    fixed_now,
) -> None:
    card = create_card(
        fixed_now,
        forward_step_index=3,
        reverse_step_index=3,
        forward_due_in_days=0,
        reverse_due_in_days=0,
    )
    test_dependencies["phrase_repository"].add(card)
    fixed_clock.current = fixed_now

    forward = test_use_cases["submit_review_answer"].execute(
        SubmitReviewAnswerCommand(
            user_id=1,
            card_id=card.id,
            direction=ReviewDirection.FORWARD,
            answer_text="buena suerte",
        )
    )
    reverse = test_use_cases["submit_review_answer"].execute(
        SubmitReviewAnswerCommand(
            user_id=1,
            card_id=card.id,
            direction=ReviewDirection.REVERSE,
            answer_text="good luck",
        )
    )

    assert forward.learning_status is LearningStatus.ACTIVE
    assert reverse.learning_status is LearningStatus.LEARNED


def test_submit_review_answer_raises_when_not_due_or_disabled(
    test_use_cases,
    fixed_clock,
    fixed_now,
) -> None:
    result = test_use_cases["translate_phrase"].execute(
        TranslatePhraseCommand(user_id=1, text="good luck")
    )

    with pytest.raises(ReviewNotAvailableError):
        test_use_cases["submit_review_answer"].execute(
            SubmitReviewAnswerCommand(
                user_id=1,
                card_id=result.card_id,
                direction=ReviewDirection.FORWARD,
                answer_text="buena suerte",
            )
        )

    test_use_cases["toggle_learning"].execute(
        ToggleLearningCommand(
            user_id=1,
            card_id=result.card_id,
            learning_enabled=False,
        )
    )
    fixed_clock.current = fixed_now + timedelta(days=2)

    with pytest.raises(LearningDisabledError):
        test_use_cases["submit_review_answer"].execute(
            SubmitReviewAnswerCommand(
                user_id=1,
                card_id=result.card_id,
                direction=ReviewDirection.FORWARD,
                answer_text="buena suerte",
            )
        )


def test_toggle_learning_and_progress_aggregate_status_counts(
    test_use_cases,
    fixed_clock,
    fixed_now,
) -> None:
    active = test_use_cases["translate_phrase"].execute(
        TranslatePhraseCommand(user_id=1, text="good luck")
    )
    disabled = test_use_cases["translate_phrase"].execute(
        TranslatePhraseCommand(user_id=1, text="hello", learn=False)
    )
    test_use_cases["toggle_learning"].execute(
        ToggleLearningCommand(
            user_id=1,
            card_id=disabled.card_id,
            learning_enabled=True,
        )
    )
    fixed_clock.current = fixed_now + timedelta(days=2)
    test_use_cases["submit_review_answer"].execute(
        SubmitReviewAnswerCommand(
            user_id=1,
            card_id=active.card_id,
            direction=ReviewDirection.FORWARD,
            answer_text="buena suerte",
        )
    )

    snapshot = test_use_cases["get_user_progress"].execute(
        GetUserProgressQuery(user_id=1)
    )

    assert snapshot.total_cards == 2
    assert snapshot.active_cards == 2
    assert snapshot.completed_review_tracks == 0
    assert snapshot.total_review_tracks == 4


def test_update_and_get_settings_validate_and_preserve_notification_day(
    test_dependencies,
    test_use_cases,
) -> None:
    repository = test_dependencies["settings_repository"]
    saved = repository.save(
        default_settings(1).mark_notification_sent(date(2026, 3, 28))
    )

    updated = test_use_cases["update_settings"].execute(
        UpdateSettingsCommand(
            user_id=1,
            default_source_lang=" EN ",
            default_target_lang="pt_BR",
            default_translation_direction=ReviewDirection.REVERSE,
            timezone="Europe/Moscow",
            notification_time_local=time(hour=8, minute=15),
            notifications_enabled=False,
        )
    )
    fetched = test_use_cases["get_settings"].execute(
        GetSettingsQuery(user_id=1)
    )

    assert saved.last_notification_local_date == date(2026, 3, 28)
    assert updated.default_source_lang == "en"
    assert updated.default_target_lang == "pt-br"
    assert updated.default_translation_direction is ReviewDirection.REVERSE
    assert fetched.notifications_enabled is False
    assert repository.get(1).last_notification_local_date == date(2026, 3, 28)


@pytest.mark.parametrize(
    ("source_lang", "target_lang", "timezone_name", "message"),
    [
        ("en", "en", "UTC", "Source and target languages must differ."),
        ("english", "es", "UTC", "Source language code is invalid."),
        ("en", "spanish", "UTC", "Target language code is invalid."),
        ("en", "es", "Mars/Colony", "Timezone must be a valid IANA timezone."),
    ],
)
def test_update_settings_rejects_invalid_values(
    test_use_cases,
    source_lang: str,
    target_lang: str,
    timezone_name: str,
    message: str,
) -> None:
    with pytest.raises(InvalidSettingsError, match=message):
        test_use_cases["update_settings"].execute(
            UpdateSettingsCommand(
                user_id=1,
                default_source_lang=source_lang,
                default_target_lang=target_lang,
                default_translation_direction=ReviewDirection.FORWARD,
                timezone=timezone_name,
                notification_time_local=time(hour=9),
                notifications_enabled=True,
            )
        )


def test_quiz_session_start_resume_skip_and_submit_flow(
    test_use_cases,
    fixed_clock,
    fixed_now,
) -> None:
    translated = test_use_cases["translate_phrase"].execute(
        TranslatePhraseCommand(user_id=1, text="good luck")
    )
    fixed_clock.current = fixed_now + timedelta(days=2)

    first_prompt = test_use_cases["start_quiz_session"].execute(user_id=1)
    resumed_prompt = test_use_cases["start_quiz_session"].execute(user_id=1)
    skipped = test_use_cases["skip_quiz_session"].execute(user_id=1)
    restarted_prompt = test_use_cases["start_quiz_session"].execute(user_id=1)
    answered = test_use_cases["submit_active_quiz_answer"].execute(
        user_id=1,
        answer_text="buena suerte",
    )

    assert first_prompt.card_id == translated.card_id
    assert resumed_prompt.card_id == translated.card_id
    assert skipped is True
    assert restarted_prompt.card_id == translated.card_id
    assert answered.review_result.outcome is ReviewOutcome.CORRECT
    assert answered.next_prompt is not None
    assert answered.next_prompt.direction is ReviewDirection.REVERSE


def test_quiz_session_handles_missing_and_stale_sessions(
    test_dependencies,
    test_use_cases,
    fixed_clock,
    fixed_now,
) -> None:
    repository = test_dependencies["quiz_session_repository"]
    stale_card = create_card(
        fixed_now,
        learning_status=LearningStatus.NOT_LEARNING,
        forward_due_in_days=0,
        reverse_due_in_days=0,
    )
    test_dependencies["phrase_repository"].add(stale_card)
    repository.save(
        TelegramQuizSession(
            user_id=1,
            card_id=stale_card.id,
            direction=ReviewDirection.FORWARD,
            started_at=fixed_now,
        )
    )
    fixed_clock.current = fixed_now

    assert test_use_cases["start_quiz_session"].execute(user_id=1) is None
    assert repository.get(1) is None

    with pytest.raises(QuizSessionNotFoundError):
        test_use_cases["submit_active_quiz_answer"].execute(
            user_id=1,
            answer_text="buena suerte",
        )
