"""Pydantic models for learning toggle endpoints."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from spaced_repetition_bot.domain.enums import LearningStatus


class ToggleLearningRequest(BaseModel):
    """Payload for learning enable/disable switch."""

    user_id: int = Field(description="Telegram user id.", examples=[123456789])
    learning_enabled: bool = Field(
        description="Whether the card should remain in learning.",
        examples=[False],
    )


class LearningStateResponse(BaseModel):
    """Minimal card state after toggling learning."""

    card_id: UUID = Field(
        description="Card identifier.",
        examples=["11111111-1111-1111-1111-111111111111"],
    )
    learning_status: LearningStatus = Field(
        description="Current learning status.", examples=["not_learning"]
    )
