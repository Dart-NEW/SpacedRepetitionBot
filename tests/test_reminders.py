"""Reminder delivery tests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import pytest

from spaced_repetition_bot.application.dtos import TranslatePhraseCommand
from spaced_repetition_bot.infrastructure.reminders import (
    TelegramReminderService,
)
from tests.support import build_test_context


@dataclass(slots=True)
class FakeBot:
    """Minimal async bot stub for reminder delivery."""

    sent_messages: list[tuple[int, str]] = field(default_factory=list)

    async def send_message(self, user_id: int, text: str) -> None:
        self.sent_messages.append((user_id, text))


def test_send_due_reminders_sends_message_and_marks_notification_day() -> None:
    context = build_test_context(
        datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
    )
    context["translate"].execute(
        TranslatePhraseCommand(user_id=1, text="good luck")
    )
    context["clock"].current += timedelta(days=2)
    service = TelegramReminderService(
        settings_repository=context["settings_repository"],
        get_due_reviews_use_case=context["due"],
        clock=context["clock"],
    )
    bot = FakeBot()

    asyncio.run(service.send_due_reminders(bot))

    assert bot.sent_messages == [
        (
            1,
            "You have 2 due review(s). "
            "Use /quiz to continue your spaced repetition session.",
        )
    ]
    settings = context["settings_repository"].get(1)
    assert settings is not None
    assert settings.last_notification_local_date == date(2026, 3, 30)


def test_run_loops_until_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = build_test_context(
        datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
    )
    service = TelegramReminderService(
        settings_repository=context["settings_repository"],
        get_due_reviews_use_case=context["due"],
        clock=context["clock"],
        poll_interval_seconds=5,
    )
    bot = FakeBot()
    events: list[object] = []

    async def fake_send_due_reminders(
        _self: TelegramReminderService,
        received_bot: FakeBot,
    ) -> None:
        events.append(received_bot)

    async def fake_sleep(seconds: int) -> None:
        events.append(seconds)
        raise asyncio.CancelledError

    monkeypatch.setattr(
        TelegramReminderService,
        "send_due_reminders",
        fake_send_due_reminders,
    )
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(service.run(bot))

    assert events == [bot, 5]
