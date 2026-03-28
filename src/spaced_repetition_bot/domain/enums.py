"""Domain enums."""

from enum import StrEnum


class LearningStatus(StrEnum):
    """Learning lifecycle for a card."""

    ACTIVE = "active"
    NOT_LEARNING = "not_learning"
    LEARNED = "learned"


class ReviewDirection(StrEnum):
    """Supported quiz directions."""

    FORWARD = "forward"
    REVERSE = "reverse"


class ReviewOutcome(StrEnum):
    """Possible quiz outcomes."""

    CORRECT = "correct"
    INCORRECT = "incorrect"
