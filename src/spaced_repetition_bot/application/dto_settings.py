"""Settings-related application DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time


@dataclass(frozen=True, slots=True)
class GetSettingsQuery:
    """Query for user settings."""

    user_id: int


@dataclass(frozen=True, slots=True)
class UserSettingsSnapshot:
    """Public settings DTO."""

    user_id: int
    default_source_lang: str
    default_target_lang: str
    timezone: str
    notification_time_local: time
    notifications_enabled: bool


@dataclass(frozen=True, slots=True)
class UpdateSettingsCommand:
    """Command for updating settings."""

    user_id: int
    default_source_lang: str
    default_target_lang: str
    timezone: str
    notification_time_local: time
    notifications_enabled: bool
