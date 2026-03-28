"""Use case for learning state toggles."""

from __future__ import annotations

from dataclasses import dataclass

from spaced_repetition_bot.application.ports import PhraseRepository
from spaced_repetition_bot.application.toggle_learning_command import (
    ToggleLearningCommand,
)
from spaced_repetition_bot.application.use_case_common import load_user_card
from spaced_repetition_bot.domain.models import PhraseCard


@dataclass(slots=True)
class ToggleLearningUseCase:
    """Enable or disable learning for a card."""

    phrase_repository: PhraseRepository

    def execute(self, command: ToggleLearningCommand) -> PhraseCard:
        card = load_user_card(
            self.phrase_repository, command.card_id, command.user_id
        )
        updated_card = self._next_state(card, command.learning_enabled)
        return self.phrase_repository.save(updated_card)

    @staticmethod
    def _next_state(card: PhraseCard, learning_enabled: bool) -> PhraseCard:
        if learning_enabled:
            return card.enable_learning()
        return card.disable_learning()
