"""History endpoint registration."""

from __future__ import annotations

from fastapi import APIRouter, Query

from spaced_repetition_bot.application.dtos import GetHistoryQuery
from spaced_repetition_bot.bootstrap import ApplicationContainer
from spaced_repetition_bot.presentation.api_history_models import (
    HistoryItemResponse,
)


def add_history_routes(
    router: APIRouter, container: ApplicationContainer
) -> None:
    """Register history routes."""

    @router.get(
        "/history",
        response_model=list[HistoryItemResponse],
        summary="Get translation history",
        description="Return recent translation history for a user.",
        responses={
            200: {
                "description": "Recent history rows.",
                "content": {
                    "application/json": {
                        "example": [
                            {
                                "card_id": (
                                    "11111111-1111-1111-1111-111111111111"
                                ),
                                "source_text": "good luck",
                                "translated_text": "good luck (es)",
                                "source_lang": "en",
                                "target_lang": "es",
                                "created_at": "2026-03-28T12:00:00Z",
                                "learning_status": "active",
                            }
                        ]
                    }
                },
            }
        },
    )
    def get_history(
        user_id: int = Query(
            description="Telegram user id.", examples=[123456789]
        ),
        limit: int = Query(
            default=20,
            ge=1,
            le=100,
            description="Maximum number of history rows to return.",
            examples=[20],
        ),
    ) -> list[HistoryItemResponse]:
        items = container.get_history.execute(
            GetHistoryQuery(user_id=user_id, limit=limit)
        )
        return [
            HistoryItemResponse.model_validate(item, from_attributes=True)
            for item in items
        ]
