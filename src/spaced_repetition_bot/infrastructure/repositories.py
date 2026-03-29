"""Repository adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker, selectinload

from spaced_repetition_bot.domain.enums import (
    LearningStatus,
    ReviewDirection,
    ReviewOutcome,
)
from spaced_repetition_bot.domain.models import (
    PhraseCard,
    ReviewTrack,
    TelegramQuizSession,
    UserSettings,
)
from spaced_repetition_bot.infrastructure.database import (
    PhraseCardRecord,
    ReviewTrackRecord,
    TelegramQuizSessionRecord,
    UserSettingsRecord,
)


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass(slots=True)
class InMemoryPhraseRepository:
    """Simple in-memory storage for phrase cards."""

    _cards: dict[UUID, PhraseCard] = field(default_factory=dict)

    def add(self, card: PhraseCard) -> PhraseCard:
        self._cards[card.id] = card
        return card

    def save(self, card: PhraseCard) -> PhraseCard:
        self._cards[card.id] = card
        return card

    def get(self, card_id: UUID) -> PhraseCard | None:
        return self._cards.get(card_id)

    def list_by_user(self, user_id: int) -> list[PhraseCard]:
        return [
            card for card in self._cards.values() if card.user_id == user_id
        ]


@dataclass(slots=True)
class InMemorySettingsRepository:
    """Simple in-memory storage for user settings."""

    _settings: dict[int, UserSettings] = field(default_factory=dict)

    def get(self, user_id: int) -> UserSettings | None:
        return self._settings.get(user_id)

    def save(self, settings: UserSettings) -> UserSettings:
        self._settings[settings.user_id] = settings
        return settings

    def list_all(self) -> list[UserSettings]:
        return list(self._settings.values())


@dataclass(slots=True)
class InMemoryQuizSessionRepository:
    """In-memory storage for active quiz sessions."""

    _sessions: dict[int, TelegramQuizSession] = field(default_factory=dict)

    def get(self, user_id: int) -> TelegramQuizSession | None:
        return self._sessions.get(user_id)

    def save(self, session: TelegramQuizSession) -> TelegramQuizSession:
        self._sessions[session.user_id] = session
        return session

    def delete(self, user_id: int) -> None:
        self._sessions.pop(user_id, None)


def _record_to_track(record: ReviewTrackRecord) -> ReviewTrack:
    return ReviewTrack(
        direction=ReviewDirection(record.direction),
        step_index=record.step_index,
        next_review_at=_normalize_datetime(record.next_review_at),
        review_count=record.review_count,
        last_outcome=(
            ReviewOutcome(record.last_outcome) if record.last_outcome else None
        ),
        completed_at=_normalize_datetime(record.completed_at),
    )


def _record_to_card(record: PhraseCardRecord) -> PhraseCard:
    track_map = {
        ReviewDirection(track.direction): _record_to_track(track)
        for track in record.review_tracks
    }
    return PhraseCard(
        id=UUID(record.id),
        user_id=record.user_id,
        source_text=record.source_text,
        target_text=record.target_text,
        source_lang=record.source_lang,
        target_lang=record.target_lang,
        created_at=_normalize_datetime(record.created_at),
        learning_status=LearningStatus(record.learning_status),
        review_tracks=(
            track_map[ReviewDirection.FORWARD],
            track_map[ReviewDirection.REVERSE],
        ),
        archived_reason=record.archived_reason,
    )


def _record_to_settings(record: UserSettingsRecord) -> UserSettings:
    return UserSettings(
        user_id=record.user_id,
        default_source_lang=record.default_source_lang,
        default_target_lang=record.default_target_lang,
        default_translation_direction=ReviewDirection(
            record.default_translation_direction
        ),
        timezone=record.timezone,
        notification_time_local=record.notification_time_local,
        notifications_enabled=record.notifications_enabled,
        last_notification_local_date=record.last_notification_local_date,
    )


def _record_to_quiz_session(
    record: TelegramQuizSessionRecord,
) -> TelegramQuizSession:
    return TelegramQuizSession(
        user_id=record.user_id,
        card_id=UUID(record.card_id),
        direction=ReviewDirection(record.direction),
        started_at=_normalize_datetime(record.started_at),
    )


def _apply_card(record: PhraseCardRecord, card: PhraseCard) -> None:
    record.user_id = card.user_id
    record.source_text = card.source_text
    record.target_text = card.target_text
    record.source_lang = card.source_lang
    record.target_lang = card.target_lang
    record.created_at = _normalize_datetime(card.created_at)
    record.learning_status = card.learning_status.value
    record.archived_reason = card.archived_reason

    existing_by_direction = {
        ReviewDirection(track.direction): track
        for track in record.review_tracks
    }
    next_tracks: list[ReviewTrackRecord] = []
    for track in card.review_tracks:
        current = existing_by_direction.get(track.direction)
        if current is None:
            current = ReviewTrackRecord(direction=track.direction.value)
        current.direction = track.direction.value
        current.step_index = track.step_index
        current.next_review_at = _normalize_datetime(track.next_review_at)
        current.review_count = track.review_count
        current.last_outcome = (
            track.last_outcome.value if track.last_outcome else None
        )
        current.completed_at = _normalize_datetime(track.completed_at)
        next_tracks.append(current)
    record.review_tracks = next_tracks


@dataclass(slots=True)
class SqlAlchemyPhraseRepository:
    """SQLAlchemy-backed card repository."""

    session_factory: sessionmaker

    def add(self, card: PhraseCard) -> PhraseCard:
        with self.session_factory() as session:
            record = PhraseCardRecord(id=str(card.id))
            _apply_card(record, card)
            session.add(record)
            session.commit()
            return self._get_committed(session, card.id)

    def save(self, card: PhraseCard) -> PhraseCard:
        with self.session_factory() as session:
            record = session.execute(
                select(PhraseCardRecord)
                .options(selectinload(PhraseCardRecord.review_tracks))
                .where(PhraseCardRecord.id == str(card.id))
            ).scalar_one_or_none()
            if record is None:
                record = PhraseCardRecord(id=str(card.id))
                session.add(record)
            _apply_card(record, card)
            session.commit()
            return self._get_committed(session, card.id)

    def get(self, card_id: UUID) -> PhraseCard | None:
        with self.session_factory() as session:
            record = session.execute(
                select(PhraseCardRecord)
                .options(selectinload(PhraseCardRecord.review_tracks))
                .where(PhraseCardRecord.id == str(card_id))
            ).scalar_one_or_none()
            if record is None:
                return None
            return _record_to_card(record)

    def list_by_user(self, user_id: int) -> list[PhraseCard]:
        with self.session_factory() as session:
            records = session.execute(
                select(PhraseCardRecord)
                .options(selectinload(PhraseCardRecord.review_tracks))
                .where(PhraseCardRecord.user_id == user_id)
            ).scalars()
            return [_record_to_card(record) for record in records]

    def _get_committed(self, session, card_id: UUID) -> PhraseCard:
        record = session.execute(
            select(PhraseCardRecord)
            .options(selectinload(PhraseCardRecord.review_tracks))
            .where(PhraseCardRecord.id == str(card_id))
        ).scalar_one()
        return _record_to_card(record)


@dataclass(slots=True)
class SqlAlchemySettingsRepository:
    """SQLAlchemy-backed settings repository."""

    session_factory: sessionmaker

    def get(self, user_id: int) -> UserSettings | None:
        with self.session_factory() as session:
            record = session.get(UserSettingsRecord, user_id)
            if record is None:
                return None
            return _record_to_settings(record)

    def save(self, settings: UserSettings) -> UserSettings:
        with self.session_factory() as session:
            record = session.get(UserSettingsRecord, settings.user_id)
            if record is None:
                record = UserSettingsRecord(user_id=settings.user_id)
                session.add(record)
            record.default_source_lang = settings.default_source_lang
            record.default_target_lang = settings.default_target_lang
            record.default_translation_direction = (
                settings.default_translation_direction.value
            )
            record.timezone = settings.timezone
            record.notification_time_local = settings.notification_time_local
            record.notifications_enabled = settings.notifications_enabled
            record.last_notification_local_date = (
                settings.last_notification_local_date
            )
            session.commit()
            return _record_to_settings(record)

    def list_all(self) -> list[UserSettings]:
        with self.session_factory() as session:
            records = session.execute(select(UserSettingsRecord)).scalars()
            return [_record_to_settings(record) for record in records]


@dataclass(slots=True)
class SqlAlchemyQuizSessionRepository:
    """SQLAlchemy-backed quiz session repository."""

    session_factory: sessionmaker

    def get(self, user_id: int) -> TelegramQuizSession | None:
        with self.session_factory() as session:
            record = session.get(TelegramQuizSessionRecord, user_id)
            if record is None:
                return None
            return _record_to_quiz_session(record)

    def save(self, quiz_session: TelegramQuizSession) -> TelegramQuizSession:
        with self.session_factory() as session:
            record = session.get(
                TelegramQuizSessionRecord, quiz_session.user_id
            )
            if record is None:
                record = TelegramQuizSessionRecord(
                    user_id=quiz_session.user_id
                )
                session.add(record)
            record.card_id = str(quiz_session.card_id)
            record.direction = quiz_session.direction.value
            record.started_at = _normalize_datetime(quiz_session.started_at)
            session.commit()
            return _record_to_quiz_session(record)

    def delete(self, user_id: int) -> None:
        with self.session_factory() as session:
            record = session.get(TelegramQuizSessionRecord, user_id)
            if record is not None:
                session.delete(record)
                session.commit()
