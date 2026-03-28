"""Typed commands, queries and result DTOs."""

from spaced_repetition_bot.application.dto_history import (
    GetHistoryQuery,
    HistoryItem,
)
from spaced_repetition_bot.application.dto_progress import (
    GetUserProgressQuery,
    UserProgressSnapshot,
)
from spaced_repetition_bot.application.dto_reviews import (
    DueReviewItem,
    ReviewAnswerResult,
    SubmitReviewAnswerCommand,
)
from spaced_repetition_bot.application.dto_settings import (
    GetSettingsQuery,
    UpdateSettingsCommand,
    UserSettingsSnapshot,
)
from spaced_repetition_bot.application.dto_translation import (
    ScheduledReviewItem,
    TranslatePhraseCommand,
    TranslationGatewayResult,
    TranslationResult,
)
from spaced_repetition_bot.application.toggle_learning_command import (
    ToggleLearningCommand,
)

__all__ = [
    "DueReviewItem",
    "GetHistoryQuery",
    "GetSettingsQuery",
    "GetUserProgressQuery",
    "HistoryItem",
    "ReviewAnswerResult",
    "ScheduledReviewItem",
    "SubmitReviewAnswerCommand",
    "ToggleLearningCommand",
    "TranslatePhraseCommand",
    "TranslationGatewayResult",
    "TranslationResult",
    "UpdateSettingsCommand",
    "UserProgressSnapshot",
    "UserSettingsSnapshot",
]
