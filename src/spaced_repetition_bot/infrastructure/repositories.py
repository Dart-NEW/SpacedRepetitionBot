"""Public repository exports.

The concrete implementations are split across focused internal modules so the
legacy import path remains stable while the maintainability index improves.
"""

from spaced_repetition_bot.infrastructure._repositories_memory import (
    InMemoryPhraseRepository,
    InMemoryQuizSessionRepository,
    InMemorySettingsRepository,
    NORMALIZED_MATCH_DASHES,
    SQLITE_WRITE_LOCK,
    _apply_card,
    _apply_settings,
    _deserialize_pending_reviews,
    _needs_normalized_fallback,
    _normalize_datetime,
    _normalize_match_text,
    _record_to_card,
    _record_to_quiz_session,
    _record_to_settings,
    _record_to_track,
    _serialize_pending_reviews,
    _sqlite_write_lock_for,
)
from spaced_repetition_bot.infrastructure._repositories_sqlalchemy import (
    SqlAlchemyPhraseRepository,
    SqlAlchemyQuizSessionRepository,
    SqlAlchemySettingsRepository,
)

__all__ = [
    "InMemoryPhraseRepository",
    "InMemoryQuizSessionRepository",
    "InMemorySettingsRepository",
    "NORMALIZED_MATCH_DASHES",
    "SQLITE_WRITE_LOCK",
    "SqlAlchemyPhraseRepository",
    "SqlAlchemyQuizSessionRepository",
    "SqlAlchemySettingsRepository",
    "_apply_card",
    "_apply_settings",
    "_deserialize_pending_reviews",
    "_needs_normalized_fallback",
    "_normalize_datetime",
    "_normalize_match_text",
    "_record_to_card",
    "_record_to_quiz_session",
    "_record_to_settings",
    "_record_to_track",
    "_serialize_pending_reviews",
    "_sqlite_write_lock_for",
]
