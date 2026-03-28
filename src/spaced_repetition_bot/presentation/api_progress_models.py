"""Pydantic models for progress endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProgressResponse(BaseModel):
    """Aggregated user progress."""

    total_cards: int = Field(
        description="Total number of cards.", examples=[12]
    )
    active_cards: int = Field(
        description="Cards still in learning.", examples=[8]
    )
    learned_cards: int = Field(
        description="Cards fully learned.", examples=[2]
    )
    not_learning_cards: int = Field(
        description="Cards excluded from learning.", examples=[2]
    )
    due_reviews: int = Field(
        description="Reviews currently due.", examples=[3]
    )
    completed_review_tracks: int = Field(
        description="Completed directional tracks.", examples=[7]
    )
    total_review_tracks: int = Field(
        description="Total directional tracks.", examples=[24]
    )
