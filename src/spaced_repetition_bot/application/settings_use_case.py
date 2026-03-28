"""Use cases for user settings."""

from __future__ import annotations

from dataclasses import dataclass

from spaced_repetition_bot.application.dto_settings import (
    GetSettingsQuery,
    UpdateSettingsCommand,
    UserSettingsSnapshot,
)
from spaced_repetition_bot.application.ports import SettingsRepository
from spaced_repetition_bot.application.use_case_common import (
    default_settings,
    map_settings_snapshot,
)
from spaced_repetition_bot.domain.models import UserSettings


@dataclass(slots=True)
class GetSettingsUseCase:
    """Return user settings, creating defaults on the fly."""

    settings_repository: SettingsRepository

    def execute(self, query: GetSettingsQuery) -> UserSettingsSnapshot:
        settings = self.settings_repository.get(
            query.user_id
        ) or default_settings(query.user_id)
        return map_settings_snapshot(settings)


@dataclass(slots=True)
class UpdateSettingsUseCase:
    """Persist updated user settings."""

    settings_repository: SettingsRepository

    def execute(self, command: UpdateSettingsCommand) -> UserSettingsSnapshot:
        settings = UserSettings(
            user_id=command.user_id,
            default_source_lang=command.default_source_lang,
            default_target_lang=command.default_target_lang,
            timezone=command.timezone,
            notification_time_local=command.notification_time_local,
            notifications_enabled=command.notifications_enabled,
        )
        stored = self.settings_repository.save(settings)
        return map_settings_snapshot(stored)
