"""Application-layer errors."""


class ApplicationError(Exception):
    """Base class for application errors."""


class CardNotFoundError(ApplicationError):
    """Raised when a card does not exist."""


class LearningDisabledError(ApplicationError):
    """Raised when the user tries to review a disabled card."""


class ReviewNotAvailableError(ApplicationError):
    """Raised when the requested review is not due."""


class InvalidSettingsError(ApplicationError):
    """Raised when user settings are invalid."""


class QuizSessionNotFoundError(ApplicationError):
    """Raised when a Telegram quiz session is missing."""
