"""Learning toggle endpoint registration."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Body, Path

from spaced_repetition_bot.application.dtos import ToggleLearningCommand
from spaced_repetition_bot.application.errors import ApplicationError
from spaced_repetition_bot.bootstrap import ApplicationContainer
from spaced_repetition_bot.presentation.api_errors import to_http_exception
from spaced_repetition_bot.presentation.api_learning_models import (
    LearningStateResponse,
    ToggleLearningRequest,
)


def add_learning_routes(
    router: APIRouter, container: ApplicationContainer
) -> None:
    """Register learning toggle routes."""

    @router.patch(
        "/cards/{card_id}/learning",
        response_model=LearningStateResponse,
        summary="Enable or disable learning",
        description="Toggle whether a card participates in future reviews.",
        responses={
            200: {
                "description": "Learning state updated.",
                "content": {
                    "application/json": {
                        "example": {
                            "card_id": "11111111-1111-1111-1111-111111111111",
                            "learning_status": "not_learning",
                        }
                    }
                },
            },
            404: {
                "description": "Card not found.",
                "content": {
                    "application/json": {
                        "example": {"detail": "Card not found."}
                    }
                },
            },
        },
    )
    def toggle_learning(
        payload: ToggleLearningRequest = Body(
            description="Learning toggle request.",
            examples=[{"user_id": 123456789, "learning_enabled": False}],
        ),
        card_id: UUID = Path(
            description="Card identifier.",
            examples=["11111111-1111-1111-1111-111111111111"],
        ),
    ) -> LearningStateResponse:
        try:
            card = container.toggle_learning.execute(
                ToggleLearningCommand(
                    user_id=payload.user_id,
                    card_id=card_id,
                    learning_enabled=payload.learning_enabled,
                )
            )
        except ApplicationError as error:
            raise to_http_exception(error) from error
        return LearningStateResponse(
            card_id=card.id, learning_status=card.learning_status
        )
