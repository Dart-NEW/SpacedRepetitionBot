"""Infrastructure database and repository tests."""

from __future__ import annotations

from datetime import date, datetime, time, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.pool import StaticPool

from spaced_repetition_bot.domain.enums import (
    LearningStatus,
    ReviewDirection,
)
from spaced_repetition_bot.domain.models import (
    TelegramQuizSession,
    UserSettings,
)
from spaced_repetition_bot.infrastructure.database import (
    build_engine,
    build_session_factory,
    initialize_database,
)
from spaced_repetition_bot.infrastructure.repositories import (
    InMemoryPhraseRepository,
    InMemoryQuizSessionRepository,
    InMemorySettingsRepository,
    SqlAlchemyPhraseRepository,
    SqlAlchemyQuizSessionRepository,
    SqlAlchemySettingsRepository,
    _normalize_datetime,
)
from tests.support import build_session_factory_for_tests, create_card

pytestmark = pytest.mark.integration


def test_normalize_datetime_handles_none_naive_and_aware_values() -> None:
    naive = datetime(2026, 3, 28, 12, 0)
    aware = datetime(2026, 3, 28, 15, 0, tzinfo=timezone.utc)

    assert _normalize_datetime(None) is None
    assert _normalize_datetime(naive).tzinfo == timezone.utc
    assert _normalize_datetime(aware) == aware


def test_build_engine_uses_static_pool_for_memory_sqlite() -> None:
    memory_engine = build_engine("sqlite:///:memory:")
    file_engine = build_engine("sqlite:///./test.db")

    assert isinstance(memory_engine.pool, StaticPool)
    assert memory_engine.url.database == ":memory:"
    assert file_engine.url.database.endswith("test.db")
    memory_engine.dispose()
    file_engine.dispose()


def test_initialize_database_and_session_factory_create_working_schema(
) -> None:
    engine = build_engine("sqlite:///:memory:")
    initialize_database(engine)
    session_factory = build_session_factory(engine)

    with session_factory() as session:
        assert session.execute(text("SELECT 1")).scalar_one() == 1
    engine.dispose()


def test_in_memory_repositories_cover_basic_crud(fixed_now) -> None:
    phrase_repository = InMemoryPhraseRepository()
    settings_repository = InMemorySettingsRepository()
    quiz_repository = InMemoryQuizSessionRepository()

    card = create_card(fixed_now)
    phrase_repository.add(card)
    phrase_repository.save(card.disable_learning())

    settings = UserSettings(user_id=1)
    settings_repository.save(settings)

    session = TelegramQuizSession(
        user_id=1,
        card_id=card.id,
        direction=ReviewDirection.FORWARD,
        started_at=fixed_now,
    )
    quiz_repository.save(session)

    assert (
        phrase_repository.get(card.id).learning_status
        is LearningStatus.NOT_LEARNING
    )
    assert settings_repository.get(1) == settings
    assert settings_repository.list_all() == [settings]
    assert quiz_repository.get(1) == session

    quiz_repository.delete(1)

    assert quiz_repository.get(1) is None


def test_sqlalchemy_phrase_repository_round_trip_preserves_tracks(
    fixed_now,
) -> None:
    session_factory = build_session_factory_for_tests()
    repository = SqlAlchemyPhraseRepository(session_factory)
    card = create_card(
        fixed_now,
        forward_step_index=2,
        reverse_step_index=1,
        archived_reason="archived",
    )

    stored = repository.add(card)
    loaded = repository.get(card.id)
    listed = repository.list_by_user(card.user_id)

    assert stored.id == card.id
    assert loaded.archived_reason == "archived"
    assert loaded.review_tracks[0].step_index == 2
    assert loaded.review_tracks[1].step_index == 1
    assert listed[0].id == card.id
    session_factory._test_engine.dispose()


def test_sqlalchemy_phrase_repository_save_upserts_new_and_existing_cards(
    fixed_now,
) -> None:
    session_factory = build_session_factory_for_tests()
    repository = SqlAlchemyPhraseRepository(session_factory)
    card = create_card(fixed_now)

    saved = repository.save(card)
    updated = repository.save(card.disable_learning())

    assert saved.id == card.id
    assert updated.learning_status is LearningStatus.NOT_LEARNING
    session_factory._test_engine.dispose()


def test_sqlalchemy_settings_repository_round_trip_preserves_fields() -> None:
    session_factory = build_session_factory_for_tests()
    repository = SqlAlchemySettingsRepository(session_factory)
    settings = UserSettings(
        user_id=7,
        default_source_lang="de",
        default_target_lang="it",
        default_translation_direction=ReviewDirection.REVERSE,
        timezone="Europe/Berlin",
        notification_time_local=time(hour=8, minute=15),
        notifications_enabled=False,
        last_notification_local_date=date(2026, 3, 28),
    )

    saved = repository.save(settings)

    assert saved.default_translation_direction is ReviewDirection.REVERSE
    assert repository.get(7).timezone == "Europe/Berlin"
    assert repository.list_all()[0].last_notification_local_date == date(
        2026, 3, 28
    )
    session_factory._test_engine.dispose()


def test_sqlalchemy_quiz_session_repository_round_trip(fixed_now) -> None:
    session_factory = build_session_factory_for_tests()
    phrase_repository = SqlAlchemyPhraseRepository(session_factory)
    card = phrase_repository.save(create_card(fixed_now))
    repository = SqlAlchemyQuizSessionRepository(session_factory)
    quiz_session = TelegramQuizSession(
        user_id=1,
        card_id=card.id,
        direction=ReviewDirection.REVERSE,
        started_at=fixed_now,
    )

    saved = repository.save(quiz_session)

    assert saved.direction is ReviewDirection.REVERSE
    assert repository.get(1).card_id == card.id

    repository.delete(1)

    assert repository.get(1) is None
    session_factory._test_engine.dispose()
