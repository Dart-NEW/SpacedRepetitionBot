"""Pydantic models for review endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from spaced_repetition_bot.domain.enums import (
    LearningStatus,
    ReviewDirection,
    ReviewOutcome,
)


class DueReviewResponse(BaseModel):
    """Due review prompt."""

    card_id: UUID = Field(
        description="Card identifier.",
        examples=["11111111-1111-1111-1111-111111111111"],
    )
    direction: ReviewDirection = Field(
        description="Quiz direction.", examples=["forward"]
    )
    prompt_text: str = Field(
        description="Text shown to the learner.", examples=["good luck"]
    )
    due_at: datetime = Field(
        description="Due timestamp.", examples=["2026-03-30T12:00:00Z"]
    )
    step_index: int = Field(description="Current review step.", examples=[0])


class ReviewAnswerRequest(BaseModel):
    """Payload for a manual quiz answer."""

    user_id: int = Field(description="Telegram user id.", examples=[123456789])
    direction: ReviewDirection = Field(
        description="Quiz direction.", examples=["forward"]
    )
    answer_text: str = Field(
        description="Manual answer entered by the user.",
        examples=["buena suerte"],
    )


class ReviewAnswerResponse(BaseModel):
    """Result of a quiz answer."""

    card_id: UUID = Field(
        description="Card identifier.",
        examples=["11111111-1111-1111-1111-111111111111"],
    )
    direction: ReviewDirection = Field(
        description="Quiz direction.", examples=["forward"]
    )
    outcome: ReviewOutcome = Field(
        description="Review result.", examples=["correct"]
    )
    expected_answer: str = Field(
        description="Expected answer used for evaluation.",
        examples=["buena suerte"],
    )
    provided_answer: str = Field(
        description="User answer.", examples=["buena suerte"]
    )
    step_index: int = Field(description="Updated step index.", examples=[1])
    next_review_at: datetime | None = Field(
        description="Next due datetime or null if learned.",
        examples=["2026-04-02T12:00:00Z"],
    )
    learning_status: LearningStatus = Field(
        description="Card learning status.", examples=["active"]
    )
