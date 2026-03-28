"""Settings endpoint registration."""

from __future__ import annotations

from fastapi import APIRouter, Body, Query

from spaced_repetition_bot.application.dtos import (
    GetSettingsQuery,
    UpdateSettingsCommand,
)
from spaced_repetition_bot.bootstrap import ApplicationContainer
from spaced_repetition_bot.presentation.api_settings_models import (
    SettingsResponse,
    UpdateSettingsRequest,
)


def add_settings_routes(
    router: APIRouter, container: ApplicationContainer
) -> None:
    """Register settings routes."""

    @router.get(
        "/settings",
        response_model=SettingsResponse,
        summary="Get user settings",
        description="Return current user settings or defaults.",
        responses={
            200: {
                "description": "User settings.",
                "content": {
                    "application/json": {
                        "example": {
                            "user_id": 123456789,
                            "default_source_lang": "en",
                            "default_target_lang": "es",
                            "timezone": "Europe/Moscow",
                            "notification_time_local": "09:00:00",
                            "notifications_enabled": True,
                        }
                    }
                },
            }
        },
    )
    def get_settings(
        user_id: int = Query(
            description="Telegram user id.", examples=[123456789]
        ),
    ) -> SettingsResponse:
        result = container.get_settings.execute(
            GetSettingsQuery(user_id=user_id)
        )
        return SettingsResponse.model_validate(result, from_attributes=True)

    @router.put(
        "/settings",
        response_model=SettingsResponse,
        summary="Update user settings",
        description=(
            "Persist settings that influence translation defaults "
            "and notifications."
        ),
        responses={
            200: {
                "description": "Settings updated.",
                "content": {
                    "application/json": {
                        "example": {
                            "user_id": 123456789,
                            "default_source_lang": "en",
                            "default_target_lang": "es",
                            "timezone": "Europe/Moscow",
                            "notification_time_local": "09:00:00",
                            "notifications_enabled": True,
                        }
                    }
                },
            }
        },
    )
    def update_settings(
        payload: UpdateSettingsRequest = Body(
            description="Settings payload.",
            examples=[
                {
                    "user_id": 123456789,
                    "default_source_lang": "en",
                    "default_target_lang": "es",
                    "timezone": "Europe/Moscow",
                    "notification_time_local": "09:00:00",
                    "notifications_enabled": True,
                }
            ],
        ),
    ) -> SettingsResponse:
        result = container.update_settings.execute(
            UpdateSettingsCommand(
                user_id=payload.user_id,
                default_source_lang=payload.default_source_lang,
                default_target_lang=payload.default_target_lang,
                timezone=payload.timezone,
                notification_time_local=payload.notification_time_local,
                notifications_enabled=payload.notifications_enabled,
            )
        )
        return SettingsResponse.model_validate(result, from_attributes=True)
