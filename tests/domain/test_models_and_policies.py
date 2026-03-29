"""Domain model and policy tests."""

from __future__ import annotations

from datetime import timedelta

import pytest

from spaced_repetition_bot.domain.enums import (
    LearningStatus,
    ReviewDirection,
    ReviewOutcome,
)
from spaced_repetition_bot.domain.models import ReviewTrack, UserSettings
from spaced_repetition_bot.domain.policies import (
    FixedIntervalSpacedRepetitionPolicy,
    NormalizedTextAnswerPolicy,
)
from tests.support import create_card

pytestmark = pytest.mark.unit


def test_review_track_due_logic(fixed_now) -> None:
    completed = ReviewTrack(
        direction=ReviewDirection.FORWARD,
        next_review_at=fixed_now,
        completed_at=fixed_now,
    )
    unscheduled = ReviewTrack(direction=ReviewDirection.REVERSE)
    future = ReviewTrack(
        direction=ReviewDirection.REVERSE,
        next_review_at=fixed_now + timedelta(minutes=1),
    )
    due = ReviewTrack(
        direction=ReviewDirection.FORWARD,
        next_review_at=fixed_now,
    )

    assert completed.is_due(fixed_now) is False
    assert unscheduled.is_due(fixed_now) is False
    assert future.is_due(fixed_now) is False
    assert due.is_due(fixed_now) is True


def test_phrase_card_prompt_expected_answer_and_track_selection(
    fixed_now,
) -> None:
    card = create_card(fixed_now)

    assert card.track_for(ReviewDirection.FORWARD).direction is ReviewDirection.FORWARD
    assert card.prompt_for(ReviewDirection.FORWARD) == "good luck"
    assert card.prompt_for(ReviewDirection.REVERSE) == "buena suerte"
    assert card.expected_answer_for(ReviewDirection.FORWARD) == "buena suerte"
    assert card.expected_answer_for(ReviewDirection.REVERSE) == "good luck"


def test_replace_track_marks_card_as_learned_only_when_both_tracks_completed(
    fixed_now,
) -> None:
    card = create_card(
        fixed_now,
        reverse_due_in_days=None,
        reverse_completed=True,
    )
    updated_track = ReviewTrack(
        direction=ReviewDirection.FORWARD,
        step_index=4,
        next_review_at=None,
        completed_at=fixed_now,
    )

    updated = card.replace_track(updated_track)

    assert updated.is_fully_learned is True
    assert updated.learning_status is LearningStatus.LEARNED


def test_disable_and_enable_learning_restore_expected_status(fixed_now) -> None:
    active_card = create_card(fixed_now)
    learned_card = create_card(
        fixed_now,
        learning_status=LearningStatus.LEARNED,
        forward_due_in_days=None,
        reverse_due_in_days=None,
        forward_completed=True,
        reverse_completed=True,
    )

    disabled = active_card.disable_learning()

    assert disabled.learning_status is LearningStatus.NOT_LEARNING
    assert disabled.archived_reason == "user_opt_out"
    assert disabled.enable_learning().learning_status is LearningStatus.ACTIVE
    assert learned_card.enable_learning().learning_status is LearningStatus.LEARNED


def test_fixed_interval_policy_initializes_both_tracks_and_advances_schedule(
    fixed_now,
) -> None:
    policy = FixedIntervalSpacedRepetitionPolicy()
    forward, reverse = policy.initialize_tracks(fixed_now)

    assert forward.direction is ReviewDirection.FORWARD
    assert reverse.direction is ReviewDirection.REVERSE
    assert forward.next_review_at == fixed_now + timedelta(days=2)
    assert reverse.next_review_at == fixed_now + timedelta(days=2)

    advanced = policy.apply_outcome(
        track=forward,
        now=fixed_now + timedelta(days=2),
        outcome=ReviewOutcome.CORRECT,
    )

    assert advanced.step_index == 1
    assert advanced.next_review_at == fixed_now + timedelta(days=5)
    assert advanced.review_count == 1
    assert advanced.last_outcome is ReviewOutcome.CORRECT


def test_fixed_interval_policy_resets_on_incorrect_answer(fixed_now) -> None:
    policy = FixedIntervalSpacedRepetitionPolicy()
    track = ReviewTrack(
        direction=ReviewDirection.FORWARD,
        step_index=2,
        next_review_at=fixed_now,
        review_count=3,
    )

    reset = policy.apply_outcome(
        track=track,
        now=fixed_now,
        outcome=ReviewOutcome.INCORRECT,
    )

    assert reset.step_index == 0
    assert reset.next_review_at == fixed_now + timedelta(days=2)
    assert reset.review_count == 4
    assert reset.last_outcome is ReviewOutcome.INCORRECT
    assert reset.completed_at is None


def test_fixed_interval_policy_marks_last_step_completed(fixed_now) -> None:
    policy = FixedIntervalSpacedRepetitionPolicy()
    track = ReviewTrack(
        direction=ReviewDirection.FORWARD,
        step_index=3,
        next_review_at=fixed_now,
    )

    completed = policy.apply_outcome(
        track=track,
        now=fixed_now,
        outcome=ReviewOutcome.CORRECT,
    )

    assert completed.step_index == 4
    assert completed.next_review_at is None
    assert completed.completed_at == fixed_now


def test_answer_policy_normalizes_case_whitespace_and_dash_variants() -> None:
    policy = NormalizedTextAnswerPolicy()

    assert policy.normalize("  Buena—Suerte  ") == "buena suerte"
    assert policy.is_correct(
        expected="buena suerte",
        provided=" BUENA_suerte ",
    )


def test_user_settings_pair_direction_and_notification_marking(
    fixed_now,
) -> None:
    settings = UserSettings(user_id=1)

    assert settings.translation_pair_for(ReviewDirection.FORWARD) == (
        "en",
        "es",
    )
    assert settings.translation_pair_for(ReviewDirection.REVERSE) == (
        "es",
        "en",
    )
    assert settings.mark_notification_sent(
        local_date=fixed_now.date()
    ).last_notification_local_date == fixed_now.date()
