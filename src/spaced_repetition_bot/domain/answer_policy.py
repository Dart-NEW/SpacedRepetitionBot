"""Answer evaluation policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class AnswerEvaluationPolicy(Protocol):
    """Contract for answer evaluation."""

    def is_correct(self, expected: str, provided: str) -> bool:
        """Return whether the provided answer should be accepted."""


@dataclass(frozen=True, slots=True)
class NormalizedTextAnswerPolicy:
    """Simple but deterministic normalization for manual answers."""

    def is_correct(self, expected: str, provided: str) -> bool:
        """Compare normalized strings."""

        return self.normalize(expected) == self.normalize(provided)

    @staticmethod
    def normalize(value: str) -> str:
        """Normalize user input for robust string comparison."""

        return " ".join(value.strip().casefold().split())
