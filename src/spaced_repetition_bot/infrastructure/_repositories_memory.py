"""Shared repository helpers and in-memory implementations.

The public `infrastructure.repositories` module re-exports the classes and
helpers from this module together with the SQLAlchemy-backed implementations.
"""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import json
from threading import Lock
from uuid import UUID

from spaced_repetition_bot.application.dtos import (
    DueReviewItem,
    HistoryItem,
    UserProgressSnapshot,
)
from spaced_repetition_bot.domain.enums import (
    LearningStatus,
    ReviewDirection,
    ReviewOutcome,
)
from spaced_repetition_bot.domain.models import (
    PhraseCard,
    QuizReviewPointer,
    ReviewTrack,
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

SQLITE_WRITE_LOCK = Lock()
NORMALIZED_MATCH_DASHES = (
    "-",
    "_",
    "\u2010",
    "\u2011",
    "\u2012",
    "\u2013",
    "\u2014",
    "\u2212",
)


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_match_text(value: str) -> str:
    normalized = value
    for dash in NORMALIZED_MATCH_DASHES:
        normalized = normalized.replace(dash, " ")
    return " ".join(normalized.strip().casefold().split())


def _needs_normalized_fallback(value: str) -> bool:
    return _normalize_match_text(value) != value.strip().casefold()


def _sqlite_write_lock_for(session):
    bind = session.get_bind()
    if bind is None or bind.dialect.name != "sqlite":
        return nullcontext()
    return SQLITE_WRITE_LOCK


def _serialize_pending_reviews(
    pending_reviews: tuple[QuizReviewPointer, ...],
) -> str:
    return json.dumps(
        [
            {
                "card_id": str(item.card_id),
                "direction": item.direction.value,
            }
            for item in pending_reviews
        ]
    )


def _deserialize_pending_reviews(raw_value: str | None) -> (
    tuple[QuizReviewPointer, ...]
):
    if not raw_value:
        return ()
    items = json.loads(raw_value)
    return tuple(
        QuizReviewPointer(
            card_id=UUID(item["card_id"]),
            direction=ReviewDirection(item["direction"]),
        )
        for item in items
    )


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

    def find_matching_card(
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

    def list_due_reviews(
        self, user_id: int, now: datetime
    ) -> list[DueReviewItem]:
        due_reviews: list[DueReviewItem] = []
        for card in self.list_by_user(user_id):
            if card.learning_status is not LearningStatus.ACTIVE:
                continue
            for track in card.review_tracks:
                if not track.is_due(now):
                    continue
                due_reviews.append(
                    DueReviewItem(
                        card_id=card.id,
                        direction=track.direction,
                        prompt_text=card.prompt_for(track.direction),
                        due_at=track.next_review_at,
                        step_index=track.step_index,
                    )
                )
        return sorted(due_reviews, key=lambda item: item.due_at)

    def get_progress_snapshot(
        self, user_id: int, now: datetime
    ) -> UserProgressSnapshot:
        cards = self.list_by_user(user_id)
        active_cards = 0
        learned_cards = 0
        not_learning_cards = 0
        due_reviews = 0
        completed_review_tracks = 0
        total_review_tracks = 0
        for card in cards:
            if card.learning_status is LearningStatus.ACTIVE:
                active_cards += 1
            elif card.learning_status is LearningStatus.LEARNED:
                learned_cards += 1
            else:
                not_learning_cards += 1
            for track in card.review_tracks:
                total_review_tracks += 1
                if track.is_completed:
                    completed_review_tracks += 1
                if (
                    card.learning_status is LearningStatus.ACTIVE
                    and track.is_due(now)
                ):
                    due_reviews += 1
        return UserProgressSnapshot(
            total_cards=len(cards),
            active_cards=active_cards,
            learned_cards=learned_cards,
            not_learning_cards=not_learning_cards,
            due_reviews=due_reviews,
            completed_review_tracks=completed_review_tracks,
            total_review_tracks=total_review_tracks,
        )


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
class InMemoryHistoryRepository:
    """In-memory storage for translation history rows."""

    _items: dict[UUID, HistoryItem] = field(default_factory=dict)

    def add(self, item: HistoryItem) -> HistoryItem:
        self._items[item.id] = item
        return item

    def save(self, item: HistoryItem) -> HistoryItem:
        existing = self._items.get(item.id)
        if existing is not None:
            item = replace(item, created_at=existing.created_at)
        self._items[item.id] = item
        return item

    def list_by_user(self, user_id: int, limit: int) -> list[HistoryItem]:
        items = sorted(
            (
                item
                for item in self._items.values()
                if item.user_id == user_id
            ),
            key=lambda item: item.created_at,
            reverse=True,
        )
        return items[:limit]


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
        notification_frequency_days=record.notification_frequency_days,
        notifications_enabled=record.notifications_enabled,
        last_notification_local_date=record.last_notification_local_date,
    )


def _record_to_history_item(record: TranslationHistoryRecord) -> HistoryItem:
    return HistoryItem(
        id=UUID(record.id),
        user_id=record.user_id,
        card_id=UUID(record.card_id) if record.card_id is not None else None,
        source_text=record.source_text,
        translated_text=record.translated_text,
        source_lang=record.source_lang,
        target_lang=record.target_lang,
        created_at=_normalize_datetime(record.created_at),
        learning_status=(
            LearningStatus(record.learning_status)
            if record.learning_status is not None
            else None
        ),
        saved=record.saved,
    )


def _record_to_quiz_session(
    record: TelegramQuizSessionRecord,
) -> TelegramQuizSession:
    return TelegramQuizSession(
        user_id=record.user_id,
        card_id=UUID(record.card_id),
        direction=ReviewDirection(record.direction),
        started_at=_normalize_datetime(record.started_at),
        pending_reviews=_deserialize_pending_reviews(
            record.pending_reviews_json
        ),
        total_prompts=record.total_prompts,
        due_reviews_total=record.due_reviews_total,
        answered_prompts=record.answered_prompts,
        correct_prompts=record.correct_prompts,
        incorrect_prompts=record.incorrect_prompts,
        awaiting_start=record.awaiting_start,
        message_id=record.message_id,
    )


def _apply_settings(
    record: UserSettingsRecord, settings: UserSettings
) -> None:
    record.default_source_lang = settings.default_source_lang
    record.default_target_lang = settings.default_target_lang
    record.default_translation_direction = (
        settings.default_translation_direction.value
    )
    record.timezone = settings.timezone
    record.notification_time_local = settings.notification_time_local
    record.notification_frequency_days = settings.notification_frequency_days
    record.notifications_enabled = settings.notifications_enabled
    record.last_notification_local_date = (
        settings.last_notification_local_date
    )


def _apply_history_item(
    record: TranslationHistoryRecord, item: HistoryItem
) -> None:
    record.user_id = item.user_id
    record.card_id = str(item.card_id) if item.card_id is not None else None
    record.source_text = item.source_text
    record.translated_text = item.translated_text
    record.source_lang = item.source_lang
    record.target_lang = item.target_lang
    record.created_at = _normalize_datetime(item.created_at)
    record.learning_status = (
        item.learning_status.value
        if item.learning_status is not None
        else None
    )
    record.saved = item.saved


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
