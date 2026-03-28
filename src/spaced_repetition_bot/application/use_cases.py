"""Application use cases."""

from spaced_repetition_bot.application.history_use_case import (
    GetHistoryUseCase,
)
from spaced_repetition_bot.application.progress_use_case import (
    GetUserProgressUseCase,
)
from spaced_repetition_bot.application.review_use_cases import (
    GetDueReviewsUseCase,
    SubmitReviewAnswerUseCase,
)
from spaced_repetition_bot.application.settings_use_case import (
    GetSettingsUseCase,
    UpdateSettingsUseCase,
)
from spaced_repetition_bot.application.toggle_learning_use_case import (
    ToggleLearningUseCase,
)
from spaced_repetition_bot.application.translation_use_case import (
    TranslatePhraseUseCase,
)

__all__ = [
    "GetDueReviewsUseCase",
    "GetHistoryUseCase",
    "GetSettingsUseCase",
    "GetUserProgressUseCase",
    "SubmitReviewAnswerUseCase",
    "ToggleLearningUseCase",
    "TranslatePhraseUseCase",
    "UpdateSettingsUseCase",
]
