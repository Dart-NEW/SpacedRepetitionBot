"""Telegram adapter tests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from uuid import uuid4

import pytest

try:
    from spaced_repetition_bot.application.dtos import (
        GetHistoryQuery,
        QuizSessionPrompt,
        QuizSessionStartResult,
        QuizSessionSummary,
        ScheduledReviewItem,
        TranslationResult,
        UserProgressSnapshot,
        UserSettingsSnapshot,
    )
    from spaced_repetition_bot.bootstrap import ApplicationContainer
    from spaced_repetition_bot.domain.enums import (
        LearningStatus,
        ReviewDirection,
    )
    from spaced_repetition_bot.infrastructure.config import AppConfig
    from spaced_repetition_bot.presentation.telegram import (
        _format_history_card,
        _format_local_datetime,
        _format_progress_card,
        _format_quiz_intro,
        _format_quiz_prompt,
        _format_settings_card,
        _format_summary,
        _format_translation_card,
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
    message_id: int = 1
    reply_markup: object | None = None
    answers: list[FakeMessage] = field(default_factory=list)

    async def answer(
        self,
        text: str,
        reply_markup: object | None = None,
    ) -> FakeMessage:
        response = FakeMessage(
            from_user=self.from_user,
            text=text,
            message_id=self.message_id + len(self.answers) + 1,
            reply_markup=reply_markup,
        )
        self.answers.append(response)
        return response


@dataclass(slots=True)
class FakeCallbackQuery:
    """Minimal Telegram callback query stub."""

    from_user: FakeUser | None
    message: FakeMessage | None
    data: str | None
    acknowledgements: list[str | None] = field(default_factory=list)

    async def answer(self, text: str | None = None) -> None:
        self.acknowledgements.append(text)


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
        end_quiz_session=use_cases["end_quiz"],
        submit_active_quiz_answer=use_cases["submit_active_quiz"],
        submit_review_answer=use_cases["answer"],
        get_user_progress=use_cases["progress"],
        get_settings=use_cases["get_settings"],
        update_settings=use_cases["update_settings"],
        settings_repository=dependencies["settings_repository"],
        clock=dependencies["clock"],
        reminder_service=NoOpReminderService(),
    )


def handler_callbacks(
    container: ApplicationContainer,
) -> dict[str, dict[str, object]]:
    """Return router callbacks keyed by callback function name."""

    router = build_telegram_router(container)
    return {
        "message": {
            handler.callback.__name__: handler.callback
            for handler in router.message.handlers
        },
        "callback": {
            handler.callback.__name__: handler.callback
            for handler in router.callback_query.handlers
        },
    }


def test_telegram_handlers_cover_start_history_progress_and_translation() -> (
    None
):
    container = build_telegram_test_container()
    callbacks = handler_callbacks(container)

    start_message = FakeMessage(from_user=FakeUser(id=1))
    asyncio.run(callbacks["message"]["handle_start"](start_message))
    assert start_message.answers[0].text.startswith(
        "Send a word or short phrase"
    )
    assert start_message.answers[0].reply_markup is not None

    help_message = FakeMessage(from_user=FakeUser(id=1))
    asyncio.run(callbacks["message"]["handle_help"](help_message))
    assert "/quiz - start or resume a review session" in help_message.answers[
        0
    ].text
    assert "/cancel - leave the current settings input flow" in (
        help_message.answers[0].text
    )

    empty_history_message = FakeMessage(from_user=FakeUser(id=1))
    asyncio.run(callbacks["message"]["handle_history"](empty_history_message))
    assert empty_history_message.answers[0].text == "History is empty."

    translation_message = FakeMessage(
        from_user=FakeUser(id=1),
        text="good luck",
    )
    asyncio.run(
        callbacks["message"]["handle_translation"](translation_message)
    )
    translation_card = translation_message.answers[0]
    assert translation_card.text.startswith("Translation\n")
    assert "good luck" in translation_card.text
    assert "-> buena suerte" in translation_card.text
    assert "Pair: en -> es" in translation_card.text
    assert translation_card.reply_markup is not None

    progress_message = FakeMessage(from_user=FakeUser(id=1))
    asyncio.run(callbacks["message"]["handle_progress"](progress_message))
    assert progress_message.answers[0].text == (
        "Progress\n"
        "Cards: 1\n"
        "Active: 1\n"
        "Learned: 0\n"
        "Paused: 0\n"
        "Due now: 0"
    )

    history_message = FakeMessage(from_user=FakeUser(id=1))
    asyncio.run(callbacks["message"]["handle_history"](history_message))
    assert history_message.answers[0].text.startswith("Recent cards\n")
    assert "good luck -> buena suerte" in history_message.answers[0].text
    assert "Learning: Active" in history_message.answers[0].text


def test_telegram_quiz_and_settings_callbacks_drive_new_ux() -> None:
    container = build_telegram_test_container()
    callbacks = handler_callbacks(container)
    user = FakeUser(id=1)

    translation_message = FakeMessage(from_user=user, text="good luck")
    asyncio.run(
        callbacks["message"]["handle_translation"](translation_message)
    )
    container.clock.current = datetime(
        2026, 3, 30, 12, 0, tzinfo=timezone.utc
    )

    quiz_message = FakeMessage(from_user=user)
    asyncio.run(callbacks["message"]["handle_quiz"](quiz_message))
    intro_card = quiz_message.answers[0]
    assert intro_card.text.startswith("Review session\n")
    assert "Due now: 2" in intro_card.text

    start_callback = FakeCallbackQuery(
        from_user=user,
        message=intro_card,
        data="quiz:start",
    )
    asyncio.run(callbacks["callback"]["handle_quiz_start"](start_callback))
    prompt_card = intro_card.answers[0]
    assert "Progress: 1/2" in prompt_card.text
    assert "Prompt: good luck" in prompt_card.text
    assert prompt_card.reply_markup is not None

    first_answer = FakeMessage(from_user=user, text="buena suerte")
    asyncio.run(callbacks["message"]["handle_translation"](first_answer))
    assert first_answer.answers[0].text.startswith("Correct\n")
    assert "Next review: in 3 days at 12:00" in first_answer.answers[0].text
    assert "Progress: 2/2" in first_answer.answers[1].text

    second_answer = FakeMessage(from_user=user, text="good luck")
    asyncio.run(callbacks["message"]["handle_translation"](second_answer))
    assert second_answer.answers[0].text.startswith("Correct\n")
    assert second_answer.answers[1].text == "Review round finished."
    assert second_answer.answers[2].text.startswith("Session complete\n")

    settings_message = FakeMessage(from_user=user)
    asyncio.run(callbacks["message"]["handle_settings"](settings_message))
    settings_card = settings_message.answers[0]
    assert settings_card.text.startswith("Settings\n")

    pair_callback = FakeCallbackQuery(
        from_user=user,
        message=settings_card,
        data="settings:pair",
    )
    asyncio.run(callbacks["callback"]["handle_settings_pair"](pair_callback))
    assert settings_card.answers[0].text.startswith(
        "Send the pair as two language codes"
    )

    pair_input = FakeMessage(from_user=user, text="de it")
    asyncio.run(callbacks["message"]["handle_translation"](pair_input))
    assert "Pair: de -> it" in pair_input.answers[0].text


def test_warning_translation_requires_explicit_keep_to_save() -> None:
    dependencies = build_test_dependencies(
        datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
    )
    dependencies["translator"].glossary[("smekh", "en", "es")] = "smekh"
    use_cases = build_test_use_cases(dependencies)
    container = ApplicationContainer(
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
        end_quiz_session=use_cases["end_quiz"],
        submit_active_quiz_answer=use_cases["submit_active_quiz"],
        submit_review_answer=use_cases["answer"],
        get_user_progress=use_cases["progress"],
        get_settings=use_cases["get_settings"],
        update_settings=use_cases["update_settings"],
        settings_repository=dependencies["settings_repository"],
        clock=dependencies["clock"],
        reminder_service=NoOpReminderService(),
    )
    callbacks = handler_callbacks(container)
    user = FakeUser(id=1)

    translation_message = FakeMessage(from_user=user, text="smekh")
    asyncio.run(
        callbacks["message"]["handle_translation"](translation_message)
    )

    warning_card = translation_message.answers[0]
    assert "Pair warning" in warning_card.text
    assert "Learning: Not saved yet" in warning_card.text
    assert (
        container.get_history.execute(GetHistoryQuery(user_id=user.id)) == []
    )

    keep_callback = FakeCallbackQuery(
        from_user=user,
        message=warning_card,
        data="translation:keep",
    )
    asyncio.run(callbacks["callback"]["handle_translation_keep"](
        keep_callback
    ))

    assert len(warning_card.answers) == 1
    assert "Learning: Active" in warning_card.answers[0].text
    history = container.get_history.execute(GetHistoryQuery(user_id=user.id))
    assert len(history) == 1
    assert history[0].source_text == "smekh"


def test_telegram_handlers_return_early_when_message_has_no_user_or_text() -> (
    None
):
    callbacks = handler_callbacks(build_telegram_test_container())

    no_user_message = FakeMessage(from_user=None, text="good luck")
    no_text_message = FakeMessage(from_user=FakeUser(id=1), text=None)

    asyncio.run(callbacks["message"]["handle_start"](no_user_message))
    asyncio.run(callbacks["message"]["handle_history"](no_user_message))
    asyncio.run(callbacks["message"]["handle_progress"](no_user_message))
    asyncio.run(callbacks["message"]["handle_translation"](no_user_message))
    asyncio.run(callbacks["message"]["handle_translation"](no_text_message))

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
            self,
            *,
            menu_button: object,
        ) -> None:
            events["menu_button"] = menu_button

    class FakeDispatcher:
        def include_router(self, router: object) -> None:
            events["router"] = router

        async def start_polling(self, bot: object) -> None:
            events["bot"] = bot

    monkeypatch.setattr(
        run_telegram_bot,
        "build_container",
        lambda: fake_container,
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
    assert len(events["commands"]) == 11
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


def test_telegram_helper_parsers_and_formatters() -> None:
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
        session_position=3,
        total_prompts=10,
    )
    formatted_prompt = _format_quiz_prompt(prompt)

    assert formatted_prompt.startswith("Quiz\n")
    assert "Progress: 3/10" in formatted_prompt
    assert "Direction: Forward" in formatted_prompt
    assert "Prompt: good luck" in formatted_prompt

    settings = UserSettingsSnapshot(
        user_id=1,
        default_source_lang="en",
        default_target_lang="es",
        default_translation_direction=ReviewDirection.FORWARD,
        timezone="Europe/Moscow",
        notification_time_local=time(hour=9, minute=30),
        notifications_enabled=True,
    )
    progress = UserProgressSnapshot(
        total_cards=12,
        active_cards=8,
        learned_cards=2,
        not_learning_cards=2,
        due_reviews=4,
        completed_review_tracks=10,
        total_review_tracks=24,
    )
    summary = QuizSessionSummary(
        total_prompts=10,
        answered_prompts=8,
        correct_prompts=7,
        incorrect_prompts=1,
        remaining_due_reviews=3,
    )
    start_result = QuizSessionStartResult(
        prompt=prompt,
        due_reviews_total=12,
        session_prompts_total=10,
        awaiting_start=True,
    )
    translation = TranslationResult(
        card_id=uuid4(),
        source_text="Smekh",
        translated_text="Smekh",
        direction=ReviewDirection.FORWARD,
        source_lang="en",
        target_lang="es",
        learning_status=LearningStatus.ACTIVE,
        provider_name="mock",
        detected_source_lang="ru",
        is_identity_translation=True,
        has_pair_warning=True,
        saved=True,
        already_saved=False,
        scheduled_reviews=(
            ScheduledReviewItem(
                direction=ReviewDirection.FORWARD,
                step_index=0,
                next_review_at=datetime(
                    2026, 3, 30, 12, 0, tzinfo=timezone.utc
                ),
                completed=False,
            ),
            ScheduledReviewItem(
                direction=ReviewDirection.REVERSE,
                step_index=0,
                next_review_at=datetime(
                    2026, 3, 30, 12, 0, tzinfo=timezone.utc
                ),
                completed=False,
            ),
        ),
    )

    assert "Reminder time: 09:30" in _format_settings_card(settings)
    assert "Due now: 4" in _format_progress_card(progress)
    assert "Tap Start to begin." in _format_quiz_intro(start_result)
    assert "Still due: 3" in _format_summary(summary)
    assert "Pair warning" in _format_translation_card(
        translation,
        due_reviews_total=2,
    )
    assert _format_local_datetime(
        datetime(2026, 3, 29, 12, 0, tzinfo=timezone.utc),
        timezone_name="UTC",
        now=datetime(2026, 3, 29, 9, 0, tzinfo=timezone.utc),
    ) == "today at 12:00"
    assert _format_local_datetime(
        datetime(2026, 3, 30, 12, 0, tzinfo=timezone.utc),
        timezone_name="UTC",
        now=datetime(2026, 3, 29, 9, 0, tzinfo=timezone.utc),
    ) == "tomorrow at 12:00"
    assert _format_history_card([]) == "History is empty."
