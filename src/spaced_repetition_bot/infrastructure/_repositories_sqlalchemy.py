"""SQLAlchemy-backed repository implementations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload, sessionmaker

from spaced_repetition_bot.application.dtos import (
    DueReviewItem,
    HistoryItem,
    UserProgressSnapshot,
)
from spaced_repetition_bot.domain.enums import (
    LearningStatus,
    ReviewDirection,
)
from spaced_repetition_bot.domain.models import (
    PhraseCard,
    TelegramQuizSession,
    UserSettings,
)
from spaced_repetition_bot.infrastructure.database import (
    PhraseCardRecord,
    ReviewTrackRecord,
    TelegramQuizSessionRecord,
    TranslationHistoryRecord,
    UserSettingsRecord,
)
from spaced_repetition_bot.infrastructure._repositories_memory import (
    _apply_card,
    _apply_history_item,
    _apply_settings,
    _needs_normalized_fallback,
    _normalize_datetime,
    _normalize_match_text,
    _record_to_card,
    _record_to_history_item,
    _record_to_quiz_session,
    _record_to_settings,
    _serialize_pending_reviews,
    _sqlite_write_lock_for,
)


@dataclass(slots=True)
class SqlAlchemyPhraseRepository:
    """SQLAlchemy-backed card repository."""

    session_factory: sessionmaker

    def add(self, card: PhraseCard) -> PhraseCard:
        with self.session_factory() as session:
            with _sqlite_write_lock_for(session):
                record = PhraseCardRecord(id=str(card.id))
                _apply_card(record, card)
                session.add(record)
                session.commit()
            return card

    def save(self, card: PhraseCard) -> PhraseCard:
        with self.session_factory() as session:
            with _sqlite_write_lock_for(session):
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
            return card

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

    def find_matching_card(
        self,
        *,
        user_id: int,
        source_text: str,
        translated_text: str,
        source_lang: str,
        target_lang: str,
    ) -> PhraseCard | None:
        normalized_source = source_text.strip().casefold()
        normalized_target = translated_text.strip().casefold()
        with self.session_factory() as session:
            record = session.execute(
                select(PhraseCardRecord)
                .options(selectinload(PhraseCardRecord.review_tracks))
                .where(
                    PhraseCardRecord.user_id == user_id,
                    PhraseCardRecord.source_lang == source_lang,
                    PhraseCardRecord.target_lang == target_lang,
                    func.lower(func.trim(PhraseCardRecord.source_text))
                    == normalized_source,
                    func.lower(func.trim(PhraseCardRecord.target_text))
                    == normalized_target,
                )
                .limit(1)
            ).scalar_one_or_none()
            if record is not None:
                return _record_to_card(record)
        if not (
            _needs_normalized_fallback(source_text)
            or _needs_normalized_fallback(translated_text)
        ):
            return None
        return self._find_matching_card_fallback(
            user_id=user_id,
            source_text=source_text,
            translated_text=translated_text,
            source_lang=source_lang,
            target_lang=target_lang,
        )

    def list_due_reviews(
        self, user_id: int, now: datetime
    ) -> list[DueReviewItem]:
        with self.session_factory() as session:
            rows = session.execute(
                select(
                    PhraseCardRecord.id,
                    PhraseCardRecord.source_text,
                    PhraseCardRecord.target_text,
                    ReviewTrackRecord.direction,
                    ReviewTrackRecord.next_review_at,
                    ReviewTrackRecord.step_index,
                )
                .join(
                    ReviewTrackRecord,
                    ReviewTrackRecord.card_id == PhraseCardRecord.id,
                )
                .where(
                    PhraseCardRecord.user_id == user_id,
                    PhraseCardRecord.learning_status
                    == LearningStatus.ACTIVE.value,
                    ReviewTrackRecord.completed_at.is_(None),
                    ReviewTrackRecord.next_review_at.is_not(None),
                    ReviewTrackRecord.next_review_at
                    <= _normalize_datetime(now),
                )
                .order_by(ReviewTrackRecord.next_review_at)
            ).all()
            return [
                DueReviewItem(
                    card_id=UUID(row.id),
                    direction=ReviewDirection(row.direction),
                    prompt_text=(
                        row.source_text
                        if row.direction == ReviewDirection.FORWARD.value
                        else row.target_text
                    ),
                    due_at=_normalize_datetime(row.next_review_at),
                    step_index=row.step_index,
                )
                for row in rows
            ]

    def get_progress_snapshot(
        self, user_id: int, now: datetime
    ) -> UserProgressSnapshot:
        now_utc = _normalize_datetime(now)
        with self.session_factory() as session:
            card_rows = session.execute(
                select(
                    PhraseCardRecord.learning_status,
                    func.count(PhraseCardRecord.id),
                )
                .where(PhraseCardRecord.user_id == user_id)
                .group_by(PhraseCardRecord.learning_status)
            ).all()
            card_counts = {row.learning_status: row[1] for row in card_rows}
            track_row = session.execute(
                select(
                    func.count(ReviewTrackRecord.id),
                    func.sum(
                        case(
                            (
                                ReviewTrackRecord.completed_at.is_not(None),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    func.sum(
                        case(
                            (
                                and_(
                                    PhraseCardRecord.learning_status
                                    == LearningStatus.ACTIVE.value,
                                    ReviewTrackRecord.completed_at.is_(None),
                                    ReviewTrackRecord.next_review_at.is_not(
                                        None
                                    ),
                                    ReviewTrackRecord.next_review_at
                                    <= now_utc,
                                ),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                )
                .select_from(PhraseCardRecord)
                .join(
                    ReviewTrackRecord,
                    ReviewTrackRecord.card_id == PhraseCardRecord.id,
                )
                .where(PhraseCardRecord.user_id == user_id)
            ).one()
        return UserProgressSnapshot(
            total_cards=sum(card_counts.values()),
            active_cards=card_counts.get(LearningStatus.ACTIVE.value, 0),
            learned_cards=card_counts.get(LearningStatus.LEARNED.value, 0),
            not_learning_cards=card_counts.get(
                LearningStatus.NOT_LEARNING.value, 0
            ),
            due_reviews=track_row[2] or 0,
            completed_review_tracks=track_row[1] or 0,
            total_review_tracks=track_row[0] or 0,
        )

    def _find_matching_card_fallback(
        self,
        *,
        user_id: int,
        source_text: str,
        translated_text: str,
        source_lang: str,
        target_lang: str,
    ) -> PhraseCard | None:
        normalized_source = _normalize_match_text(source_text).split()
        normalized_target = _normalize_match_text(translated_text).split()
        for card in self.list_by_user(user_id):
            if (
                card.source_lang != source_lang
                or card.target_lang != target_lang
            ):
                continue
            current_source = _normalize_match_text(card.source_text).split()
            current_target = _normalize_match_text(card.target_text).split()
            if (
                current_source == normalized_source
                and current_target == normalized_target
            ):
                return card
        return None


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
            with _sqlite_write_lock_for(session):
                record = session.get(UserSettingsRecord, settings.user_id)
                if record is None:
                    record = UserSettingsRecord(user_id=settings.user_id)
                    session.add(record)
                _apply_settings(record, settings)
                try:
                    session.commit()
                except IntegrityError:
                    session.rollback()
                    record = session.get(UserSettingsRecord, settings.user_id)
                    if record is None:
                        raise
                    _apply_settings(record, settings)
                    session.commit()
            return _record_to_settings(record)

    def list_all(self) -> list[UserSettings]:
        with self.session_factory() as session:
            records = session.execute(select(UserSettingsRecord)).scalars()
            return [_record_to_settings(record) for record in records]


@dataclass(slots=True)
class SqlAlchemyHistoryRepository:
    """SQLAlchemy-backed translation history repository."""

    session_factory: sessionmaker

    def add(self, item: HistoryItem) -> HistoryItem:
        with self.session_factory() as session:
            with _sqlite_write_lock_for(session):
                record = TranslationHistoryRecord(id=str(item.id))
                _apply_history_item(record, item)
                session.add(record)
                session.commit()
            return item

    def save(self, item: HistoryItem) -> HistoryItem:
        with self.session_factory() as session:
            with _sqlite_write_lock_for(session):
                record = session.get(TranslationHistoryRecord, str(item.id))
                if record is None:
                    record = TranslationHistoryRecord(id=str(item.id))
                    session.add(record)
                    _apply_history_item(record, item)
                else:
                    original_created_at = record.created_at
                    _apply_history_item(record, item)
                    record.created_at = original_created_at
                session.commit()
            return _record_to_history_item(record)

    def list_by_user(self, user_id: int, limit: int) -> list[HistoryItem]:
        with self.session_factory() as session:
            records = session.execute(
                select(TranslationHistoryRecord)
                .where(TranslationHistoryRecord.user_id == user_id)
                .order_by(TranslationHistoryRecord.created_at.desc())
                .limit(limit)
            ).scalars()
            return [_record_to_history_item(record) for record in records]


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
            with _sqlite_write_lock_for(session):
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
                record.started_at = _normalize_datetime(
                    quiz_session.started_at
                )
                record.pending_reviews_json = _serialize_pending_reviews(
                    quiz_session.pending_reviews
                )
                record.total_prompts = quiz_session.total_prompts
                record.due_reviews_total = quiz_session.due_reviews_total
                record.answered_prompts = quiz_session.answered_prompts
                record.correct_prompts = quiz_session.correct_prompts
                record.incorrect_prompts = quiz_session.incorrect_prompts
                record.awaiting_start = quiz_session.awaiting_start
                record.message_id = quiz_session.message_id
                session.commit()
            return _record_to_quiz_session(record)

    def delete(self, user_id: int) -> None:
        with self.session_factory() as session:
            with _sqlite_write_lock_for(session):
                record = session.get(TelegramQuizSessionRecord, user_id)
                if record is not None:
                    session.delete(record)
                    session.commit()
