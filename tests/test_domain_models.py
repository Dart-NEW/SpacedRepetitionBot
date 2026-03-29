"""Domain-level behavior tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from spaced_repetition_bot.domain.enums import (
    LearningStatus,
    ReviewDirection,
    ReviewOutcome,
)
from spaced_repetition_bot.domain.models import PhraseCard, ReviewTrack
from spaced_repetition_bot.domain.policies import (
    FixedIntervalSpacedRepetitionPolicy,
    NormalizedTextAnswerPolicy,
)


def build_card(now: datetime) -> PhraseCard:
    """Build a phrase card for domain tests."""

    return PhraseCard(
        id=uuid4(),
        user_id=1,
        source_text="good luck",
        target_text="buena suerte",
        source_lang="en",
        target_lang="es",
        created_at=now,
        learning_status=LearningStatus.ACTIVE,
        review_tracks=(
            ReviewTrack(
                direction=ReviewDirection.FORWARD,
                next_review_at=now + timedelta(days=2),
            ),
            ReviewTrack(
                direction=ReviewDirection.REVERSE,
                next_review_at=now + timedelta(days=2),
            ),
        ),
    )


def test_review_track_is_not_due_when_completed_or_unscheduled() -> None:
    now = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
    completed_track = ReviewTrack(
        direction=ReviewDirection.FORWARD,
        next_review_at=now,
        completed_at=now,
    )
    unscheduled_track = ReviewTrack(direction=ReviewDirection.REVERSE)

    assert completed_track.is_due(now) is False
    assert unscheduled_track.is_due(now) is False


def test_phrase_card_uses_reverse_prompt_and_expected_answer() -> None:
    now = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
    card = build_card(now)

    assert card.prompt_for(ReviewDirection.REVERSE) == "buena suerte"
    assert card.expected_answer_for(ReviewDirection.REVERSE) == "good luck"


def test_replace_track_marks_card_as_learned() -> None:
    now = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
    completed_track = ReviewTrack(
        direction=ReviewDirection.FORWARD,
        step_index=4,
        next_review_at=None,
        completed_at=now,
    )
    other_completed_track = ReviewTrack(
        direction=ReviewDirection.REVERSE,
        step_index=4,
        next_review_at=None,
        completed_at=now,
    )
    card = PhraseCard(
        id=uuid4(),
        user_id=1,
        source_text="good luck",
        target_text="buena suerte",
        source_lang="en",
        target_lang="es",
        created_at=now,
        learning_status=LearningStatus.ACTIVE,
        review_tracks=(
            ReviewTrack(
                direction=ReviewDirection.FORWARD,
                next_review_at=now + timedelta(days=2),
            ),
            other_completed_track,
        ),
    )

    updated = card.replace_track(completed_track)

    assert updated.is_fully_learned is True
    assert updated.learning_status is LearningStatus.LEARNED
    assert updated.enable_learning().learning_status is LearningStatus.LEARNED


def test_disable_and_enable_learning_restore_active_for_incomplete_card() -> (
    None
):
    now = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
    card = build_card(now)

    disabled = card.disable_learning()
    enabled = disabled.enable_learning()

    assert disabled.learning_status is LearningStatus.NOT_LEARNING
    assert disabled.archived_reason == "user_opt_out"
    assert enabled.learning_status is LearningStatus.ACTIVE
    assert enabled.archived_reason is None


def test_fixed_interval_policy_marks_track_completed_on_last_step() -> None:
    now = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
    track = ReviewTrack(
        direction=ReviewDirection.FORWARD,
        step_index=3,
        next_review_at=now,
    )

    updated = FixedIntervalSpacedRepetitionPolicy().apply_outcome(
        track=track,
        now=now,
        outcome=ReviewOutcome.CORRECT,
    )

    assert updated.step_index == 4
    assert updated.next_review_at is None
    assert updated.completed_at == now


def test_fixed_interval_policy_supports_minute_based_schedule() -> None:
    now = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
    policy = FixedIntervalSpacedRepetitionPolicy(
        intervals=(2, 3, 5, 7),
        interval_unit="minutes",
    )

    forward_track, _ = policy.initialize_tracks(now)
    updated = policy.apply_outcome(
        track=forward_track,
        now=now + timedelta(minutes=2),
        outcome=ReviewOutcome.CORRECT,
    )

    assert forward_track.next_review_at == now + timedelta(minutes=2)
    assert updated.step_index == 1
    assert updated.next_review_at == now + timedelta(minutes=5)


def test_answer_policy_normalizes_case_and_whitespace() -> None:
    policy = NormalizedTextAnswerPolicy()

    assert policy.is_correct(
        expected="buena suerte", provided="  BUENA   SUERTE "
    )
