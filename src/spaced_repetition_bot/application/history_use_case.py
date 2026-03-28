"""Use case for translation history."""

from __future__ import annotations

from dataclasses import dataclass

from spaced_repetition_bot.application.dto_history import (
    GetHistoryQuery,
    HistoryItem,
)
from spaced_repetition_bot.application.ports import PhraseRepository


@dataclass(slots=True)
class GetHistoryUseCase:
    """Return user translation history."""

    phrase_repository: PhraseRepository

    def execute(self, query: GetHistoryQuery) -> list[HistoryItem]:
        cards = sorted(
            self.phrase_repository.list_by_user(query.user_id),
            key=lambda card: card.created_at,
            reverse=True,
        )
        return [
            HistoryItem(
                card_id=card.id,
                source_text=card.source_text,
                translated_text=card.target_text,
                source_lang=card.source_lang,
                target_lang=card.target_lang,
                created_at=card.created_at,
                learning_status=card.learning_status,
            )
            for card in cards[: query.limit]
        ]
