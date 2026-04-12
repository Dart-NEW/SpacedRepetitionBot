"""Telegram reminder delivery."""

# Reminder flow:
# - This service runs inside the Telegram bot process.
# - It polls persisted user settings on a fixed interval.
# - Each iteration evaluates reminder eligibility for every stored user.
# - Eligibility depends on timezone, local reminder time, and enable state.
# - A reminder is sent only when due reviews currently exist.
# - `last_notification_local_date` enforces at most one reminder per day.
# - Invalid timezones are ignored so one bad record does not stop the loop.
# - Bot send failures are also isolated to the affected user.
# - The scheduler itself does not create or modify review state.
# - It only reads due reviews through the application use case.
# - The callback button points back to the quiz flow in Telegram.
# - Polling remains simple because this MVP does not support frequency rules.
# - A dedicated scheduler can replace this service later without API changes.
# - Keeping the logic here avoids leaking Telegram concerns into use cases.
# - Tests cover once-per-day behavior and failure isolation.
# - The loop is intentionally small so cancellation stays predictable.
# - `Clock` injection keeps time-based behavior deterministic in tests.
# - The repository is responsible for persistence, not scheduling logic.
# - This file should stay focused on delivery timing and side effects.
# - Anything user-facing beyond reminder text belongs in presentation code.

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from spaced_repetition_bot.application.use_cases import GetDueReviewsUseCase
from spaced_repetition_bot.application.ports import Clock, SettingsRepository


@dataclass(slots=True)
class TelegramReminderService:
    """Send reminder messages for due reviews."""

    settings_repository: SettingsRepository
    get_due_reviews_use_case: GetDueReviewsUseCase
    clock: Clock
    poll_interval_seconds: int = 60

    async def run(self, bot: Bot) -> None:
        """Run the reminder loop forever."""

        while True:
            await self.send_due_reminders(bot)
            await asyncio.sleep(self.poll_interval_seconds)

    async def send_due_reminders(self, bot: Bot) -> None:
        """Send reminders to users with due reviews."""

        now = self.clock.now()
        for settings in self.settings_repository.list_all():
            if not settings.notifications_enabled:
                continue
            try:
                timezone = ZoneInfo(settings.timezone)
            except ZoneInfoNotFoundError:
                continue
            local_now = now.astimezone(timezone)
            if settings.last_notification_local_date is not None and (
                local_now.date() - settings.last_notification_local_date
            ).days < settings.notification_frequency_days:
                continue
            if (
                local_now.time().replace(second=0, microsecond=0)
                < settings.notification_time_local
            ):
                continue
            due_reviews = self.get_due_reviews_use_case.execute(
                settings.user_id
            )
            if not due_reviews:
                continue
            try:
                await bot.send_message(
                    settings.user_id,
                    (
                        f"You have {len(due_reviews)} due review(s).\n"
                        "Start a short review round when you are ready."
                    ),
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text="Start quiz",
                                    callback_data="quiz:continue",
                                )
                            ]
                        ]
                    ),
                )
            except Exception:
                continue
            self.settings_repository.save(
                settings.mark_notification_sent(local_now.date())
            )
