"""Pydantic models for history endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from spaced_repetition_bot.domain.enums import LearningStatus


class HistoryItemResponse(BaseModel):
    """Single history row returned by the API."""

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
    created_at: datetime = Field(
        description="Creation timestamp.", examples=["2026-03-28T12:00:00Z"]
    )
    learning_status: LearningStatus = Field(
        description="Learning status.", examples=["active"]
    )
