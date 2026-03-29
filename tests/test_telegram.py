"""Telegram adapter tests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from uuid import uuid4

import pytest

try:
    from spaced_repetition_bot.application.dtos import QuizSessionPrompt
    from spaced_repetition_bot.bootstrap import ApplicationContainer
    from spaced_repetition_bot.domain.enums import ReviewDirection
    from spaced_repetition_bot.infrastructure.config import AppConfig
    from spaced_repetition_bot.presentation.telegram import (
        _format_quiz_prompt,
        _parse_direction,
        _parse_notification_time,
        build_telegram_router,
    )
    from spaced_repetition_bot import run_telegram_bot
    from tests.support import (
        NoOpReminderService,
        build_test_dependencies,
        build_test_use_cases,
    )
except (
    ImportError
):  # pragma: no cover - exercised in CI with full deps installed.
    pytest.skip(
        "Telegram dependencies are not installed.", allow_module_level=True
    )


@dataclass(slots=True)
class FakeUser:
    """Minimal Telegram user stub."""

    id: int


@dataclass(slots=True)
class FakeMessage:
    """Minimal Telegram message stub."""

    from_user: FakeUser | None
    text: str | None = None
    answers: list[str] = field(default_factory=list)

    async def answer(self, text: str) -> None:
        self.answers.append(text)


def build_telegram_test_container() -> ApplicationContainer:
    """Build a container suitable for Telegram adapter tests."""

    dependencies = build_test_dependencies(
        datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
    )
    use_cases = build_test_use_cases(dependencies)
    return ApplicationContainer(
        config=AppConfig(
            app_name="Telegram Test",
            app_version="1.0.0",
            api_prefix="/api/test",
        ),
        translate_phrase=use_cases["translate"],
        get_history=use_cases["get_history"],
        toggle_learning=use_cases["toggle"],
        get_due_reviews=use_cases["due"],
        start_quiz_session=use_cases["start_quiz"],
        skip_quiz_session=use_cases["skip_quiz"],
        submit_active_quiz_answer=use_cases["submit_active_quiz"],
        submit_review_answer=use_cases["answer"],
        get_user_progress=use_cases["progress"],
        get_settings=use_cases["get_settings"],
        update_settings=use_cases["update_settings"],
        settings_repository=dependencies["settings_repository"],
        clock=dependencies["clock"],
        reminder_service=NoOpReminderService(),
    )


def handler_callbacks(container: ApplicationContainer) -> dict[str, object]:
    """Return router callbacks keyed by function name."""

    router = build_telegram_router(container)
    return {
        handler.callback.__name__: handler.callback
        for handler in router.message.handlers
    }


def test_telegram_handlers_cover_start_history_progress_and_translation() -> (
    None
):
    callbacks = handler_callbacks(build_telegram_test_container())

    start_message = FakeMessage(from_user=FakeUser(id=1))
    asyncio.run(callbacks["handle_start"](start_message))
    assert start_message.answers == [
        (
            "Send a word or phrase and I will translate it using your "
            "current language pair.\n\n"
            "Quick start:\n"
            "1. /pair en es\n"
            "2. Send a phrase like good luck\n"
            "3. Use /quiz when reviews are due\n\n"
            "Use /help to see all commands."
        )
    ]

    help_message = FakeMessage(from_user=FakeUser(id=1))
    asyncio.run(callbacks["handle_help"](help_message))
    assert help_message.answers == [
        (
            "Commands:\n"
            "/quiz - review due cards\n"
            "/settings - show your current pair and reminder settings\n"
            "/progress - show how many cards are active, learned, and due\n"
            "/history - show recent cards with ids for /notlearning or "
            "/restore\n"
            "/pair <source_lang> <target_lang> - change the active pair\n"
            "/direction <forward|reverse> - switch the default direction\n"
            "/notifytime <HH:MM> - set the local reminder time\n"
            "/timezone <IANA timezone> - set your timezone\n"
            "/notifications <on|off> - enable or disable reminders\n"
            "/skip - leave the current quiz card due\n\n"
            "Tip: plain text translates the phrase and adds it to learning."
        )
    ]

    empty_history_message = FakeMessage(from_user=FakeUser(id=1))
    asyncio.run(callbacks["handle_history"](empty_history_message))
    assert empty_history_message.answers == ["History is empty."]

    translation_message = FakeMessage(
        from_user=FakeUser(id=1), text="good luck"
    )
    asyncio.run(callbacks["handle_translation"](translation_message))
    assert translation_message.answers == [
        (
            "good luck -> buena suerte\n"
            "Direction: forward\n"
            "Pair: en/es\n"
            "Learning status: active"
        )
    ]

    progress_message = FakeMessage(from_user=FakeUser(id=1))
    asyncio.run(callbacks["handle_progress"](progress_message))
    assert progress_message.answers == [
        "Cards: 1, active: 1, learned: 0, due: 0"
    ]

    history_message = FakeMessage(from_user=FakeUser(id=1))
    asyncio.run(callbacks["handle_history"](history_message))
    assert len(history_message.answers) == 1
    assert "good luck -> buena suerte" in history_message.answers[0]
    assert "Status: active" in history_message.answers[0]


def test_telegram_handlers_return_early_when_message_has_no_user_or_text() -> (
    None
):
    callbacks = handler_callbacks(build_telegram_test_container())

    no_user_message = FakeMessage(from_user=None, text="good luck")
    no_text_message = FakeMessage(from_user=FakeUser(id=1), text=None)

    asyncio.run(callbacks["handle_start"](no_user_message))
    asyncio.run(callbacks["handle_history"](no_user_message))
    asyncio.run(callbacks["handle_progress"](no_user_message))
    asyncio.run(callbacks["handle_translation"](no_user_message))
    asyncio.run(callbacks["handle_translation"](no_text_message))

    assert no_user_message.answers == []
    assert no_text_message.answers == []


def test_run_starts_polling_with_built_router(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: dict[str, object] = {}
    fake_container = build_telegram_test_container()
    fake_router = object()

    class FakeBot:
        def __init__(self, token: str) -> None:
            events["token"] = token

        async def set_my_commands(self, commands: object) -> None:
            events["commands"] = commands

        async def set_chat_menu_button(
            self, *, menu_button: object
        ) -> None:
            events["menu_button"] = menu_button

    class FakeDispatcher:
        def include_router(self, router: object) -> None:
            events["router"] = router

        async def start_polling(self, bot: object) -> None:
            events["bot"] = bot

    monkeypatch.setattr(
        run_telegram_bot, "build_container", lambda: fake_container
    )
    monkeypatch.setattr(
        run_telegram_bot,
        "build_telegram_router",
        lambda container: fake_router,
    )
    monkeypatch.setattr(run_telegram_bot, "Bot", FakeBot)
    monkeypatch.setattr(run_telegram_bot, "Dispatcher", FakeDispatcher)

    asyncio.run(run_telegram_bot.run())

    assert events["token"] == fake_container.config.telegram_bot_token
    assert events["router"] is fake_router
    assert len(events["commands"]) == 10
    assert events["commands"][0].command == "help"
    assert events["menu_button"].type == "commands"
    assert isinstance(events["bot"], FakeBot)


def test_main_delegates_to_asyncio_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: dict[str, object] = {}

    def fake_run(coroutine: object) -> None:
        called["coroutine"] = coroutine
        coroutine.close()

    monkeypatch.setattr(run_telegram_bot.asyncio, "run", fake_run)

    run_telegram_bot.main()

    assert called["coroutine"].cr_code.co_name == "run"


def test_telegram_helper_parsers_and_prompt_formatter() -> None:
    assert _parse_direction("forward") is ReviewDirection.FORWARD
    assert _parse_direction("reverse") is ReviewDirection.REVERSE
    assert _parse_direction("sideways") is None

    assert _parse_notification_time("08:15") == time(hour=8, minute=15)
    assert _parse_notification_time("24:00") is None
    assert _parse_notification_time("bad") is None

    prompt = QuizSessionPrompt(
        card_id=uuid4(),
        direction=ReviewDirection.FORWARD,
        prompt_text="good luck",
        expected_answer="buena suerte",
        step_index=0,
    )
    formatted_prompt = _format_quiz_prompt(prompt)

    assert formatted_prompt.startswith("Quiz\n")
    assert "Direction: forward" in formatted_prompt
    assert "Prompt: good luck" in formatted_prompt
