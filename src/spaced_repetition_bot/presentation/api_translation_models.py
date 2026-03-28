"""Pydantic models for translation endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from spaced_repetition_bot.domain.enums import (
    LearningStatus,
    ReviewDirection,
)


class ScheduledReviewResponse(BaseModel):
    """Scheduled review details."""

    model_config = ConfigDict(from_attributes=True)

    direction: ReviewDirection = Field(
        description="Quiz direction.", examples=["forward"]
    )
    step_index: int = Field(
        description="Current review step index.", examples=[0]
    )
    next_review_at: datetime | None = Field(
        description="When the next review is due.",
        examples=["2026-03-30T12:00:00Z"],
    )
    completed: bool = Field(
        description="Whether the review track is completed.", examples=[False]
    )


class TranslationRequest(BaseModel):
    """Input payload for phrase translation."""

    user_id: int = Field(description="Telegram user id.", examples=[123456789])
    text: str = Field(
        description="Phrase to translate and optionally learn.",
        examples=["good luck"],
    )
    source_lang: str | None = Field(
        default=None,
        description=(
            "Explicit source language code. Falls back to user settings."
        ),
        examples=["en"],
    )
    target_lang: str | None = Field(
        default=None,
        description=(
            "Explicit target language code. Falls back to user settings."
        ),
        examples=["es"],
    )
    learn: bool = Field(
        default=True,
        description=(
            "Whether the phrase should be added to the learning queue."
        ),
        examples=[True],
    )


class TranslationResponse(BaseModel):
    """Output payload for a translation command."""

    card_id: UUID = Field(
        description="Card identifier.",
        examples=["11111111-1111-1111-1111-111111111111"],
    )
    source_text: str = Field(
        description="Original phrase.", examples=["good luck"]
    )
    translated_text: str = Field(
        description="Translated phrase.", examples=["buena suerte"]
    )
    source_lang: str = Field(
        description="Source language code.", examples=["en"]
    )
    target_lang: str = Field(
        description="Target language code.", examples=["es"]
    )
    learning_status: LearningStatus = Field(
        description="Learning status.", examples=["active"]
    )
    provider_name: str = Field(
        description="Translation provider name.", examples=["mock"]
    )
    scheduled_reviews: list[ScheduledReviewResponse] = Field(
        description="Review schedule for both directions."
    )
