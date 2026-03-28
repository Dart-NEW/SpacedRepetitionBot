"""Review submission endpoint registration."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Body, Path

from spaced_repetition_bot.application.dtos import SubmitReviewAnswerCommand
from spaced_repetition_bot.application.errors import ApplicationError
from spaced_repetition_bot.bootstrap import ApplicationContainer
from spaced_repetition_bot.presentation.api_errors import to_http_exception
from spaced_repetition_bot.presentation.api_review_models import (
    ReviewAnswerRequest,
    ReviewAnswerResponse,
)


def add_submit_review_routes(
    router: APIRouter, container: ApplicationContainer
) -> None:
    """Register review submission routes."""

    @router.post(
        "/reviews/{card_id}/answer",
        response_model=ReviewAnswerResponse,
        summary="Submit a review answer",
        description="Evaluate a manual answer and update the review schedule.",
        responses={
            200: {
                "description": "Answer processed.",
                "content": {
                    "application/json": {
                        "example": {
                            "card_id": "11111111-1111-1111-1111-111111111111",
                            "direction": "forward",
                            "outcome": "correct",
                            "expected_answer": "buena suerte",
                            "provided_answer": "buena suerte",
                            "step_index": 1,
                            "next_review_at": "2026-04-02T12:00:00Z",
                            "learning_status": "active",
                        }
                    }
                },
            },
            400: {
                "description": "Review is not available.",
                "content": {
                    "application/json": {
                        "example": {"detail": "Review is not due."}
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
            409: {
                "description": "Card is excluded from learning.",
                "content": {
                    "application/json": {
                        "example": {
                            "detail": "Card is excluded from learning."
                        }
                    }
                },
            },
        },
    )
    def submit_review_answer(
        card_id: UUID = Path(
            description="Card identifier.",
            examples=["11111111-1111-1111-1111-111111111111"],
        ),
        payload: ReviewAnswerRequest = Body(
            description="Review answer payload.",
            examples=[
                {
                    "user_id": 123456789,
                    "direction": "forward",
                    "answer_text": "buena suerte",
                }
            ],
        ),
    ) -> ReviewAnswerResponse:
        try:
            result = container.submit_review_answer.execute(
                SubmitReviewAnswerCommand(
                    user_id=payload.user_id,
                    card_id=card_id,
                    direction=payload.direction,
                    answer_text=payload.answer_text,
                )
            )
        except ApplicationError as error:
            raise to_http_exception(error) from error
        return ReviewAnswerResponse.model_validate(
            result, from_attributes=True
        )
