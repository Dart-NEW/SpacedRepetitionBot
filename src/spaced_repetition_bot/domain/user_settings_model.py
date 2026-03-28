"""User settings domain model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time


@dataclass(frozen=True, slots=True)
class UserSettings:
    """User-facing preferences."""

    user_id: int
    default_source_lang: str = "en"
    default_target_lang: str = "es"
    timezone: str = "UTC"
    notification_time_local: time = time(hour=9, minute=0)
    notifications_enabled: bool = True
