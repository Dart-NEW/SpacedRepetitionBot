"""Command DTO for learning state changes."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ToggleLearningCommand:
    """Command for enabling or disabling learning."""

    user_id: int
    card_id: UUID
    learning_enabled: bool
