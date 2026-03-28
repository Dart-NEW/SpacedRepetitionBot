"""Progress endpoint registration."""

from __future__ import annotations

from fastapi import APIRouter, Query

from spaced_repetition_bot.application.dtos import GetUserProgressQuery
from spaced_repetition_bot.bootstrap import ApplicationContainer
from spaced_repetition_bot.presentation.api_progress_models import (
    ProgressResponse,
)


def add_progress_routes(
    router: APIRouter, container: ApplicationContainer
) -> None:
    """Register progress routes."""

    @router.get(
        "/progress",
        response_model=ProgressResponse,
        summary="Get learning progress",
        description="Return aggregated progress metrics for a user.",
        responses={
            200: {
                "description": "Aggregated progress metrics.",
                "content": {
                    "application/json": {
                        "example": {
                            "total_cards": 12,
                            "active_cards": 8,
                            "learned_cards": 2,
                            "not_learning_cards": 2,
                            "due_reviews": 3,
                            "completed_review_tracks": 7,
                            "total_review_tracks": 24,
                        }
                    }
                },
            }
        },
    )
    def get_progress(
        user_id: int = Query(
            description="Telegram user id.", examples=[123456789]
        ),
    ) -> ProgressResponse:
        result = container.get_user_progress.execute(
            GetUserProgressQuery(user_id=user_id)
        )
        return ProgressResponse.model_validate(result, from_attributes=True)
