"""User settings domain model."""

# Settings model notes:
# - This entity stores user preferences that affect translation and reminders.
# - Default values define the out-of-the-box learning experience.
# - The active language pair is represented as source plus target language.
# - Direction is stored separately so one pair supports both quiz tracks.
# - Timezone and reminder time are persisted independently.
# - That keeps reminder calculations explicit and testable.
# - Notification enable state is a hard on/off switch for reminders.
# - The last local notification date prevents duplicate reminders per day.
# - `translation_pair_for` is the only behavior needed by current use cases.
# - It keeps pair inversion inside the model instead of scattered branches.
# - `mark_notification_sent` returns a new instance for immutability.
# - Immutability keeps updates predictable across repository boundaries.
# - The model is intentionally small because validation happens upstream.
# - Application use cases normalize and validate raw input before creation.
# - Repository adapters serialize this object without extra transformation.
# - Tests rely on these defaults when creating implicit user profiles.
# - New preference fields should remain user-facing and behavior-oriented.
# - Cross-cutting delivery logic should stay outside the domain model.
# - That keeps this entity readable despite being used in many flows.
# - It also helps the maintainability goal for the core learning settings.

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

    def translation_pair_for(
        self, direction: ReviewDirection
    ) -> tuple[str, str]:
        """Return the active source-target pair for a direction."""

        if direction is ReviewDirection.FORWARD:
            return self.default_source_lang, self.default_target_lang
        return self.default_target_lang, self.default_source_lang

    def mark_notification_sent(self, local_date: date) -> UserSettings:
        """Return settings with the reminder day updated."""

        return replace(self, last_notification_local_date=local_date)
