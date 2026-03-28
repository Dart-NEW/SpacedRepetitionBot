"""Due review endpoint registration."""

from __future__ import annotations

from fastapi import APIRouter, Query

from spaced_repetition_bot.bootstrap import ApplicationContainer
from spaced_repetition_bot.presentation.api_review_models import (
    DueReviewResponse,
)


def add_due_review_routes(
    router: APIRouter, container: ApplicationContainer
) -> None:
    """Register due review routes."""

    @router.get(
        "/reviews/due",
        response_model=list[DueReviewResponse],
        summary="Get due reviews",
        description="Return all reviews that are due for a user right now.",
        responses={
            200: {
                "description": "List of due reviews.",
                "content": {
                    "application/json": {
                        "example": [
                            {
                                "card_id": (
                                    "11111111-1111-1111-1111-111111111111"
                                ),
                                "direction": "forward",
                                "prompt_text": "good luck",
                                "due_at": "2026-03-30T12:00:00Z",
                                "step_index": 0,
                            }
                        ]
                    }
                },
            }
        },
    )
    def get_due_reviews(
        user_id: int = Query(
            description="Telegram user id.", examples=[123456789]
        ),
    ) -> list[DueReviewResponse]:
        items = container.get_due_reviews.execute(user_id=user_id)
        return [
            DueReviewResponse.model_validate(item, from_attributes=True)
            for item in items
        ]
