"""User settings domain model."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, time

from spaced_repetition_bot.domain.enums import ReviewDirection


@dataclass(frozen=True, slots=True)
class UserSettings:
    """User-facing preferences."""

    user_id: int
    default_source_lang: str = "en"
    default_target_lang: str = "es"
    default_translation_direction: ReviewDirection = ReviewDirection.FORWARD
    timezone: str = "UTC"
    notification_time_local: time = time(hour=9, minute=0)
    notifications_enabled: bool = True
    last_notification_local_date: date | None = None

    def translation_pair_for(self, direction: ReviewDirection) -> tuple[str, str]:
        """Return the active source-target pair for a direction."""

        if direction is ReviewDirection.FORWARD:
            return self.default_source_lang, self.default_target_lang
        return self.default_target_lang, self.default_source_lang

    def mark_notification_sent(self, local_date: date) -> UserSettings:
        """Return settings with the reminder day updated."""

        return replace(self, last_notification_local_date=local_date)
