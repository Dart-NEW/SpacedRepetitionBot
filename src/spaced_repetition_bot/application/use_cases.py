"""Public application use-case exports.

The implementation is split across focused internal modules to keep the public
import path stable while improving maintainability metrics.
"""

from spaced_repetition_bot.application._use_cases_core import (
    LANGUAGE_CODE_PATTERN,
    QUIZ_SESSION_LIMIT,
    GetDueReviewsUseCase,
    GetHistoryUseCase,
    GetSettingsUseCase,
    GetUserProgressUseCase,
    SubmitReviewAnswerUseCase,
    ToggleLearningUseCase,
    TranslatePhraseUseCase,
    TranslationWarningState,
    UpdateSettingsUseCase,
    build_quiz_prompt,
    build_quiz_summary,
    default_settings,
    find_existing_translation_card,
    list_due_reviews,
    load_user_card,
    map_scheduled_review,
    map_settings_snapshot,
    mix_due_reviews,
    normalize_language_code,
    normalize_text,
)
from spaced_repetition_bot.application._use_cases_quiz import (
    EndQuizSessionUseCase,
    SkipQuizSessionUseCase,
    StartQuizSessionUseCase,
    SubmitActiveQuizAnswerUseCase,
)

__all__ = [
    "LANGUAGE_CODE_PATTERN",
    "QUIZ_SESSION_LIMIT",
    "EndQuizSessionUseCase",
    "GetDueReviewsUseCase",
    "GetHistoryUseCase",
    "GetSettingsUseCase",
    "GetUserProgressUseCase",
    "SkipQuizSessionUseCase",
    "StartQuizSessionUseCase",
    "SubmitActiveQuizAnswerUseCase",
    "SubmitReviewAnswerUseCase",
    "ToggleLearningUseCase",
    "TranslatePhraseUseCase",
    "TranslationWarningState",
    "UpdateSettingsUseCase",
    "build_quiz_prompt",
    "build_quiz_summary",
    "default_settings",
    "find_existing_translation_card",
    "list_due_reviews",
    "load_user_card",
    "map_scheduled_review",
    "map_settings_snapshot",
    "mix_due_reviews",
    "normalize_language_code",
    "normalize_text",
]
