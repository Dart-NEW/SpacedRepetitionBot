"""Telegram adapter tests."""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from aiogram.filters import CommandObject

from spaced_repetition_bot.application.dtos import (
    TranslatePhraseCommand,
)
from spaced_repetition_bot.application.errors import (
    InvalidSettingsError,
    TranslationProviderError,
)
from spaced_repetition_bot.domain.enums import ReviewDirection
from tests.support import FakeMessage, FakeUser, handler_callbacks

pytestmark = pytest.mark.contract


def test_telegram_handlers_cover_start_translation_history_progress_and_settings(
    test_container,
) -> None:
    callbacks = handler_callbacks(test_container)

    start = FakeMessage(from_user=FakeUser(id=1))
    translation = FakeMessage(from_user=FakeUser(id=1), text="good luck")
    history = FakeMessage(from_user=FakeUser(id=1))
    progress = FakeMessage(from_user=FakeUser(id=1))
    settings = FakeMessage(from_user=FakeUser(id=1))

    asyncio.run(callbacks["handle_start"](start))
    asyncio.run(callbacks["handle_translation"](translation))
    asyncio.run(callbacks["handle_history"](history))
    asyncio.run(callbacks["handle_progress"](progress))
    asyncio.run(callbacks["handle_settings"](settings))

    assert "Send me a phrase" in start.answers[0]
    assert "good luck -> buena suerte" in translation.answers[0]
    assert "good luck -> buena suerte" in history.answers[0]
    assert "Cards: 1, active: 1, learned: 0, due: 0" == progress.answers[0]
    assert "Pair: en/es" in settings.answers[0]


def test_telegram_setting_commands_validate_and_update_values(
    test_container,
) -> None:
    callbacks = handler_callbacks(test_container)
    message = FakeMessage(from_user=FakeUser(id=1))

    asyncio.run(
        callbacks["handle_pair"](
            message,
            CommandObject(prefix="/", command="pair", mention=None, args="de it"),
        )
    )
    asyncio.run(
        callbacks["handle_direction"](
            message,
            CommandObject(
                prefix="/",
                command="direction",
                mention=None,
                args="reverse",
            ),
        )
    )
    asyncio.run(
        callbacks["handle_notify_time"](
            message,
            CommandObject(
                prefix="/",
                command="notifytime",
                mention=None,
                args="08:15",
            ),
        )
    )
    asyncio.run(
        callbacks["handle_timezone"](
            message,
            CommandObject(
                prefix="/",
                command="timezone",
                mention=None,
                args="Europe/Berlin",
            ),
        )
    )
    asyncio.run(
        callbacks["handle_notifications"](
            message,
            CommandObject(
                prefix="/",
                command="notifications",
                mention=None,
                args="off",
            ),
        )
    )

    assert all(answer.startswith("Settings updated.") for answer in message.answers)
    stored = test_container.settings_repository.get(1)
    assert stored.default_source_lang == "de"
    assert stored.default_translation_direction is ReviewDirection.REVERSE
    assert stored.timezone == "Europe/Berlin"
    assert stored.notifications_enabled is False


def test_telegram_commands_return_usage_errors_for_invalid_arguments(
    test_container,
) -> None:
    callbacks = handler_callbacks(test_container)
    message = FakeMessage(from_user=FakeUser(id=1))

    asyncio.run(
        callbacks["handle_pair"](
            message,
            CommandObject(prefix="/", command="pair", mention=None, args="onlyone"),
        )
    )
    asyncio.run(
        callbacks["handle_direction"](
            message,
            CommandObject(
                prefix="/",
                command="direction",
                mention=None,
                args="sideways",
            ),
        )
    )
    asyncio.run(
        callbacks["handle_notify_time"](
            message,
            CommandObject(
                prefix="/",
                command="notifytime",
                mention=None,
                args="25:61",
            ),
        )
    )
    asyncio.run(
        callbacks["handle_timezone"](
            message,
            CommandObject(prefix="/", command="timezone", mention=None, args="Nope/Zone"),
        )
    )
    asyncio.run(
        callbacks["handle_notifications"](
            message,
            CommandObject(
                prefix="/",
                command="notifications",
                mention=None,
                args="maybe",
            ),
        )
    )

    assert message.answers == [
        "Usage: /pair <source_lang> <target_lang>",
        "Usage: /direction <forward|reverse>",
        "Usage: /notifytime <HH:MM>",
        "Timezone must be a valid IANA timezone name.",
        "Usage: /notifications <on|off>",
    ]


def test_telegram_quiz_skip_toggle_restore_and_answer_flow(
    test_container,
    container_clock,
    fixed_now,
) -> None:
    callbacks = handler_callbacks(test_container)
    translated = test_container.translate_phrase.execute(
        TranslatePhraseCommand(user_id=1, text="good luck")
    )
    container_clock.current = fixed_now + timedelta(days=2)

    quiz = FakeMessage(from_user=FakeUser(id=1))
    skip = FakeMessage(from_user=FakeUser(id=1))
    restore = FakeMessage(from_user=FakeUser(id=1))
    disable = FakeMessage(from_user=FakeUser(id=1))
    answer = FakeMessage(from_user=FakeUser(id=1), text="buena suerte")

    asyncio.run(callbacks["handle_quiz"](quiz))
    asyncio.run(callbacks["handle_skip"](skip))
    asyncio.run(
        callbacks["handle_not_learning"](
            disable,
            CommandObject(
                prefix="/",
                command="notlearning",
                mention=None,
                args=str(translated.card_id),
            ),
        )
    )
    asyncio.run(
        callbacks["handle_restore"](
            restore,
            CommandObject(
                prefix="/",
                command="restore",
                mention=None,
                args=str(translated.card_id),
            ),
        )
    )
    asyncio.run(callbacks["handle_quiz"](quiz))
    asyncio.run(callbacks["handle_translation"](answer))

    assert "Quiz card:" in quiz.answers[0]
    assert skip.answers == ["Quiz session skipped. The card remains due."]
    assert "excluded from learning" in disable.answers[0]
    assert "restored to learning" in restore.answers[0]
    assert "Result: correct" in answer.answers[0]
    assert "Direction: reverse" in answer.answers[1]


def test_telegram_handlers_return_early_without_user_or_text(
    test_container,
) -> None:
    callbacks = handler_callbacks(test_container)
    no_user = FakeMessage(from_user=None, text="good luck")
    no_text = FakeMessage(from_user=FakeUser(id=1), text=None)

    asyncio.run(callbacks["handle_start"](no_user))
    asyncio.run(callbacks["handle_history"](no_user))
    asyncio.run(callbacks["handle_progress"](no_user))
    asyncio.run(callbacks["handle_translation"](no_user))
    asyncio.run(callbacks["handle_translation"](no_text))

    assert no_user.answers == []
    assert no_text.answers == []


def test_telegram_translation_handler_reports_provider_and_settings_errors(
    test_container,
    monkeypatch,
) -> None:
    callbacks = handler_callbacks(test_container)
    provider_message = FakeMessage(from_user=FakeUser(id=1), text="good luck")
    settings_message = FakeMessage(from_user=FakeUser(id=1))

    monkeypatch.setattr(
        type(test_container.translate_phrase),
        "execute",
        lambda _self, _command: (_ for _ in ()).throw(
            TranslationProviderError("boom")
        ),
    )
    asyncio.run(callbacks["handle_translation"](provider_message))

    monkeypatch.setattr(
        type(test_container.update_settings),
        "execute",
        lambda _self, _command: (_ for _ in ()).throw(
            InvalidSettingsError("bad settings")
        ),
    )
    asyncio.run(
        callbacks["handle_pair"](
            settings_message,
            CommandObject(prefix="/", command="pair", mention=None, args="en en"),
        )
    )

    assert provider_message.answers == [
        "Translation provider is unavailable right now."
    ]
    assert settings_message.answers == ["bad settings"]
