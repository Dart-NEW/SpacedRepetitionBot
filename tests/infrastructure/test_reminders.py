"""Reminder service tests."""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest

from spaced_repetition_bot.application.dtos import (
    TranslatePhraseCommand,
    UpdateSettingsCommand,
)
from spaced_repetition_bot.domain.enums import ReviewDirection
from spaced_repetition_bot.domain.models import UserSettings
from tests.support import FakeBot

pytestmark = pytest.mark.integration


async def _cancel_after_first_sleep(_seconds: int) -> None:
    raise asyncio.CancelledError


def test_send_due_reminders_sends_once_and_marks_notification_day(
    test_container,
    container_clock,
    fixed_now,
) -> None:
    test_container.update_settings.execute(
        UpdateSettingsCommand(
            user_id=1,
            default_source_lang="en",
            default_target_lang="es",
            default_translation_direction=ReviewDirection.FORWARD,
            timezone="UTC",
            notification_time_local=fixed_now.timetz().replace(tzinfo=None),
            notifications_enabled=True,
        )
    )
    test_container.translate_phrase.execute(
        TranslatePhraseCommand(
            user_id=1,
            text="good luck",
        )
    )
    container_clock.current = fixed_now + timedelta(days=2)
    bot = FakeBot()

    asyncio.run(test_container.reminder_service.send_due_reminders(bot))
    asyncio.run(test_container.reminder_service.send_due_reminders(bot))

    assert len(bot.sent_messages) == 1
    assert "due review(s)" in bot.sent_messages[0][1]
    assert (
        test_container.settings_repository.get(1).last_notification_local_date
        == container_clock.current.date()
    )


def test_send_due_reminders_skips_disabled_invalid_timezone_and_failures(
    test_container,
    container_clock,
    fixed_now,
) -> None:
    updater = test_container.update_settings.execute
    updater(
        UpdateSettingsCommand(
            user_id=1,
            default_source_lang="en",
            default_target_lang="es",
            default_translation_direction=ReviewDirection.FORWARD,
            timezone="UTC",
            notification_time_local=fixed_now.timetz().replace(tzinfo=None),
            notifications_enabled=False,
        )
    )
    updater(
        UpdateSettingsCommand(
            user_id=2,
            default_source_lang="en",
            default_target_lang="es",
            default_translation_direction=ReviewDirection.FORWARD,
            timezone="UTC",
            notification_time_local=fixed_now.timetz().replace(tzinfo=None),
            notifications_enabled=True,
        )
    )
    updater(
        UpdateSettingsCommand(
            user_id=3,
            default_source_lang="en",
            default_target_lang="es",
            default_translation_direction=ReviewDirection.FORWARD,
            timezone="UTC",
            notification_time_local=fixed_now.timetz().replace(tzinfo=None),
            notifications_enabled=True,
        )
    )
    test_container.translate_phrase.execute(
        TranslatePhraseCommand(user_id=3, text="good luck")
    )
    container_clock.current = fixed_now + timedelta(days=2)
    test_container.settings_repository.save(
        UserSettings(
            user_id=2,
            default_source_lang="en",
            default_target_lang="es",
            default_translation_direction=ReviewDirection.FORWARD,
            timezone="Bad/Timezone",
            notification_time_local=fixed_now.timetz().replace(tzinfo=None),
            notifications_enabled=True,
            last_notification_local_date=None,
        )
    )
    bot = FakeBot(raise_on_send=True)

    asyncio.run(test_container.reminder_service.send_due_reminders(bot))

    assert bot.sent_messages == []
    assert (
        test_container.settings_repository.get(3).last_notification_local_date
        is None
    )


def test_reminder_run_loops_until_cancelled(
    monkeypatch,
    test_container,
) -> None:
    calls: list[str] = []

    async def fake_send_due_reminders(_self, _bot) -> None:
        calls.append("tick")

    monkeypatch.setattr(
        type(test_container.reminder_service),
        "send_due_reminders",
        fake_send_due_reminders,
    )
    monkeypatch.setattr(asyncio, "sleep", _cancel_after_first_sleep)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(test_container.reminder_service.run(FakeBot()))

    assert calls == ["tick"]
