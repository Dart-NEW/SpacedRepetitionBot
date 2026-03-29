"""Telegram reminder delivery."""

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
            if settings.last_notification_local_date == local_now.date():
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
