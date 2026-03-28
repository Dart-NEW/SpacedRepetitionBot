"""Pydantic models for settings endpoints."""

from __future__ import annotations

from datetime import time

from pydantic import BaseModel, Field


class SettingsResponse(BaseModel):
    """User settings payload."""

    user_id: int = Field(description="Telegram user id.", examples=[123456789])
    default_source_lang: str = Field(
        description="Default source language.", examples=["en"]
    )
    default_target_lang: str = Field(
        description="Default target language.", examples=["es"]
    )
    timezone: str = Field(
        description="IANA timezone name.", examples=["Europe/Moscow"]
    )
    notification_time_local: time = Field(
        description="Preferred local notification time.",
        examples=["09:00:00"],
    )
    notifications_enabled: bool = Field(
        description="Whether notifications are enabled.",
        examples=[True],
    )


class UpdateSettingsRequest(BaseModel):
    """Payload for updating settings."""

    user_id: int = Field(description="Telegram user id.", examples=[123456789])
    default_source_lang: str = Field(
        description="Default source language code.", examples=["en"]
    )
    default_target_lang: str = Field(
        description="Default target language code.", examples=["es"]
    )
    timezone: str = Field(
        description="IANA timezone name.", examples=["Europe/Moscow"]
    )
    notification_time_local: time = Field(
        description="Preferred local notification time.",
        examples=["09:00:00"],
    )
    notifications_enabled: bool = Field(
        description="Whether notifications should be sent.",
        examples=[True],
    )
