"""Telegram adapter tests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
from datetime import datetime, time, timezone
from uuid import uuid4

import pytest
from aiogram.filters import CommandObject

from spaced_repetition_bot.application.dtos import (
    GetHistoryQuery,
    QuizSessionPrompt,
    QuizSessionStartResult,
    QuizSessionSummary,
    ScheduledReviewItem,
    TranslatePhraseCommand,
    TranslationResult,
    UserProgressSnapshot,
    UserSettingsSnapshot,
)
from spaced_repetition_bot.bootstrap import ApplicationContainer
from spaced_repetition_bot.application.errors import (
    InvalidSettingsError,
    TranslationProviderError,
)
from spaced_repetition_bot.domain.enums import LearningStatus, ReviewDirection
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
    _parse_notification_frequency_days,
    _parse_notification_time,
    build_telegram_router,
)
from tests.support import (
    FakeMessage,
    FakeUser,
    build_test_container,
    build_test_dependencies,
    build_test_use_cases,
    handler_callbacks,
)

pytestmark = pytest.mark.contract


@dataclass(slots=True)
class RichFakeMessage:
    """Telegram message stub preserving nested replies and markup."""

    from_user: FakeUser | None
    text: str | None = None
    message_id: int = 1
    reply_markup: object | None = None
    answers: list["RichFakeMessage"] = field(default_factory=list)

    async def answer(
        self,
        text: str,
        reply_markup: object | None = None,
        **_kwargs,
    ) -> "RichFakeMessage":
        response = RichFakeMessage(
            from_user=self.from_user,
            text=text,
            message_id=self.message_id + len(self.answers) + 1,
            reply_markup=reply_markup,
        )
        self.answers.append(response)
        return response


@dataclass(slots=True)
class FakeCallbackQuery:
    """Callback query stub for router callback tests."""

    from_user: FakeUser | None
    message: RichFakeMessage | None
    data: str | None
    acknowledgements: list[str | None] = field(default_factory=list)

    async def answer(self, text: str | None = None) -> None:
        self.acknowledgements.append(text)


def callback_handlers(
    container: ApplicationContainer,
) -> dict[str, dict[str, object]]:
    """Expose message and callback handlers from the telegram router."""

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


def test_telegram_handlers_cover_start_translation_history_and_progress(
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

    assert "Send a word or short phrase" in start.answers[0]
    assert "good luck" in translation.answers[0]
    assert "buena suerte" in translation.answers[0]
    assert "Recent cards" in history.answers[0]
    assert "good luck -> buena suerte" in history.answers[0]
    assert progress.answers[0] == (
        "Progress\nCards: 1\nActive: 1\nLearned: 0\nPaused: 0\nDue now: 0"
    )
    assert settings.answers[0].startswith("Settings\nPair: en -> es")


def test_telegram_setting_commands_validate_and_update_values(
    test_container,
) -> None:
    callbacks = handler_callbacks(test_container)
    message = FakeMessage(from_user=FakeUser(id=1))

    asyncio.run(
        callbacks["handle_pair"](
            message,
            CommandObject(
                prefix="/",
                command="pair",
                mention=None,
                args="de it",
            ),
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
        callbacks["handle_notify_every"](
            message,
            CommandObject(
                prefix="/",
                command="notifyevery",
                mention=None,
                args="2",
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

    assert all(answer.startswith("Settings\n") for answer in message.answers)
    assert message.answers[-1].endswith("Notifications: Off")
    stored = test_container.settings_repository.get(1)
    assert stored.default_source_lang == "de"
    assert stored.default_translation_direction is ReviewDirection.REVERSE
    assert stored.timezone == "Europe/Berlin"
    assert stored.notification_frequency_days == 2
    assert stored.notifications_enabled is False


def test_telegram_commands_return_usage_errors_for_invalid_arguments(
    test_container,
) -> None:
    callbacks = handler_callbacks(test_container)
    message = FakeMessage(from_user=FakeUser(id=1))

    asyncio.run(
        callbacks["handle_pair"](
            message,
            CommandObject(
                prefix="/",
                command="pair",
                mention=None,
                args="onlyone",
            ),
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
            CommandObject(
                prefix="/",
                command="timezone",
                mention=None,
                args="Nope/Zone",
            ),
        )
    )
    asyncio.run(
        callbacks["handle_notify_every"](
            message,
            CommandObject(
                prefix="/",
                command="notifyevery",
                mention=None,
                args="zero",
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
                args="maybe",
            ),
        )
    )

    assert message.answers == [
        "Usage: /pair <source_lang> <target_lang>\nExample: /pair en es",
        "Usage: /direction <forward|reverse>\nExample: /direction reverse",
        "Usage: /notifytime <HH:MM>\nExample: /notifytime 09:30",
        "Timezone must be a valid IANA timezone name.",
        "Usage: /notifyevery <days>\nExample: /notifyevery 2",
        "Usage: /notifications <on|off>\nExample: /notifications off",
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
    answer = FakeMessage(from_user=FakeUser(id=1), text="good luck")

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
    asyncio.run(callbacks["handle_translation"](answer))

    assert quiz.answers == [
        (
            "Review session\nDue now: 2\nPrompts in this round: 2\n\n"
            "Tap Start to begin."
        )
    ]
    assert skip.answers == [
        "Card skipped. It stays due.",
        (
            "Quiz\nProgress: 1/2\nDirection: Reverse\nPrompt: buena "
            "suerte\n\nType your answer below."
        ),
    ]
    assert "was paused.\nLearning: Paused" in disable.answers[0]
    assert "was restored.\nLearning: Active" in restore.answers[0]
    assert answer.answers[0].startswith("Correct\nExpected: good luck")
    assert answer.answers[1] == "Review round finished."


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
            CommandObject(
                prefix="/",
                command="pair",
                mention=None,
                args="en en",
            ),
        )
    )

    assert provider_message.answers == [
        "Translation provider is unavailable right now."
    ]
    assert settings_message.answers == ["bad settings"]


def test_telegram_callback_flow_covers_quiz_start_and_guided_settings(
) -> None:
    test_container = build_test_container(
        datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
    )
    callbacks = callback_handlers(test_container)
    user = FakeUser(id=1)

    translation_message = RichFakeMessage(from_user=user, text="good luck")
    asyncio.run(
        callbacks["message"]["handle_translation"](translation_message)
    )
    test_container.clock.current = datetime(
        2026, 3, 30, 12, 0, tzinfo=timezone.utc
    )

    quiz_message = RichFakeMessage(from_user=user)
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

    first_answer = RichFakeMessage(from_user=user, text="buena suerte")
    asyncio.run(callbacks["message"]["handle_translation"](first_answer))
    assert first_answer.answers[0].text.startswith("Correct\n")
    assert "Next review:" in first_answer.answers[0].text
    assert "Progress: 2/2" in first_answer.answers[1].text

    second_answer = RichFakeMessage(from_user=user, text="good luck")
    asyncio.run(callbacks["message"]["handle_translation"](second_answer))
    assert second_answer.answers[0].text.startswith("Correct\n")
    assert second_answer.answers[1].text == "Review round finished."
    assert second_answer.answers[2].text.startswith("Session complete\n")

    settings_message = RichFakeMessage(from_user=user)
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

    pair_input = RichFakeMessage(from_user=user, text="de it")
    asyncio.run(callbacks["message"]["handle_translation"](pair_input))
    assert "Pair: de -> it" in pair_input.answers[0].text

    notify_every_callback = FakeCallbackQuery(
        from_user=user,
        message=settings_card,
        data="settings:notifyevery",
    )
    asyncio.run(
        callbacks["callback"]["handle_settings_notify_every"](
            notify_every_callback
        )
    )
    assert settings_card.answers[1].text.startswith(
        "Send the reminder frequency"
    )

    notify_every_input = RichFakeMessage(from_user=user, text="3")
    asyncio.run(callbacks["message"]["handle_translation"](notify_every_input))
    assert (
        "Reminder frequency: Every 3 days"
        in notify_every_input.answers[0].text
    )


def test_warning_translation_requires_explicit_keep_callback() -> None:
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
        translate_phrase=use_cases["translate_phrase"],
        get_history=use_cases["get_history"],
        toggle_learning=use_cases["toggle_learning"],
        get_due_reviews=use_cases["get_due_reviews"],
        start_quiz_session=use_cases["start_quiz_session"],
        skip_quiz_session=use_cases["skip_quiz_session"],
        end_quiz_session=use_cases["end_quiz_session"],
        submit_active_quiz_answer=use_cases["submit_active_quiz_answer"],
        submit_review_answer=use_cases["submit_review_answer"],
        get_user_progress=use_cases["get_user_progress"],
        get_settings=use_cases["get_settings"],
        update_settings=use_cases["update_settings"],
        settings_repository=dependencies["settings_repository"],
        clock=dependencies["clock"],
        reminder_service=build_test_container(
            datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
        ).reminder_service,
    )
    callbacks = callback_handlers(container)
    user = FakeUser(id=1)

    translation_message = RichFakeMessage(from_user=user, text="smekh")
    asyncio.run(
        callbacks["message"]["handle_translation"](translation_message)
    )

    warning_card = translation_message.answers[0]
    assert "Pair warning" in warning_card.text
    assert "Learning: Not saved yet" in warning_card.text
    preview_history = container.get_history.execute(
        GetHistoryQuery(user_id=user.id)
    )
    assert len(preview_history) == 1
    assert preview_history[0].saved is False
    assert preview_history[0].card_id is None

    keep_callback = FakeCallbackQuery(
        from_user=user,
        message=warning_card,
        data="translation:keep",
    )
    asyncio.run(
        callbacks["callback"]["handle_translation_keep"](keep_callback)
    )

    assert len(warning_card.answers) == 1
    assert "Learning: Active" in warning_card.answers[0].text
    history = container.get_history.execute(GetHistoryQuery(user_id=user.id))
    assert len(history) == 1
    assert history[0].id == preview_history[0].id
    assert history[0].source_text == "smekh"
    assert history[0].saved is True


def test_telegram_helper_parsers_and_formatters() -> None:
    assert _parse_direction("forward") is ReviewDirection.FORWARD
    assert _parse_direction("reverse") is ReviewDirection.REVERSE
    assert _parse_direction("sideways") is None

    assert _parse_notification_time("08:15") == time(hour=8, minute=15)
    assert _parse_notification_time("24:00") is None
    assert _parse_notification_time("bad") is None
    assert _parse_notification_frequency_days("2") == 2
    assert _parse_notification_frequency_days("0") is None
    assert _parse_notification_frequency_days("bad") is None

    prompt = QuizSessionPrompt(
        card_id=uuid4(),
        direction=ReviewDirection.FORWARD,
        prompt_text="good luck",
        expected_answer="buena suerte",
        step_index=0,
        session_position=3,
        total_prompts=10,
    )
    settings = UserSettingsSnapshot(
        user_id=1,
        default_source_lang="en",
        default_target_lang="es",
        default_translation_direction=ReviewDirection.FORWARD,
        timezone="Europe/Moscow",
        notification_time_local=time(hour=9, minute=30),
        notification_frequency_days=2,
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
        history_entry_id=uuid4(),
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

    assert "Progress: 3/10" in _format_quiz_prompt(prompt)
    assert "Reminder time: 09:30" in _format_settings_card(settings)
    assert "Reminder frequency: Every 2 days" in _format_settings_card(
        settings
    )
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


def test_telegram_dashboard_and_settings_callbacks_cover_buttons() -> None:
    test_container = build_test_container(
        datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
    )
    callbacks = callback_handlers(test_container)
    user = FakeUser(id=1)

    translation_message = RichFakeMessage(from_user=user, text="good luck")
    asyncio.run(
        callbacks["message"]["handle_translation"](translation_message)
    )

    root_message = RichFakeMessage(from_user=user)
    progress_callback = FakeCallbackQuery(
        from_user=user,
        message=root_message,
        data="dashboard:progress",
    )
    history_callback = FakeCallbackQuery(
        from_user=user,
        message=root_message,
        data="dashboard:history",
    )
    translate_callback = FakeCallbackQuery(
        from_user=user,
        message=root_message,
        data="dashboard:translate",
    )
    settings_callback = FakeCallbackQuery(
        from_user=user,
        message=root_message,
        data="settings:open",
    )
    direction_callback = FakeCallbackQuery(
        from_user=user,
        message=root_message,
        data="settings:direction:reverse",
    )
    notifications_callback = FakeCallbackQuery(
        from_user=user,
        message=root_message,
        data="settings:notifications:off",
    )

    asyncio.run(
        callbacks["callback"]["handle_dashboard_progress"](
            progress_callback
        )
    )
    asyncio.run(
        callbacks["callback"]["handle_dashboard_history"](history_callback)
    )
    asyncio.run(
        callbacks["callback"]["handle_dashboard_translate"](
            translate_callback
        )
    )
    asyncio.run(
        callbacks["callback"]["handle_settings_open"](settings_callback)
    )
    asyncio.run(
        callbacks["callback"]["handle_settings_direction"](
            direction_callback
        )
    )
    asyncio.run(
        callbacks["callback"]["handle_settings_notifications"](
            notifications_callback
        )
    )

    assert root_message.answers[0].text.startswith("Progress\n")
    assert root_message.answers[1].text.startswith("Recent cards\n")
    assert root_message.answers[2].text == (
        "Send any word or phrase and I will translate it."
    )
    assert root_message.answers[3].text.startswith("Settings\n")
    assert "Direction: Reverse" in root_message.answers[4].text
    assert root_message.answers[5].text.endswith("Notifications: Off")


def test_telegram_guided_input_and_cancel_flow() -> None:
    test_container = build_test_container(
        datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
    )
    callbacks = callback_handlers(test_container)
    user = FakeUser(id=1)
    root_message = RichFakeMessage(from_user=user)

    pair_callback = FakeCallbackQuery(
        from_user=user,
        message=root_message,
        data="settings:pair",
    )
    notify_callback = FakeCallbackQuery(
        from_user=user,
        message=root_message,
        data="settings:notifytime",
    )
    timezone_callback = FakeCallbackQuery(
        from_user=user,
        message=root_message,
        data="settings:timezone",
    )

    asyncio.run(callbacks["callback"]["handle_settings_pair"](pair_callback))
    bad_pair = RichFakeMessage(from_user=user, text="onlyone")
    asyncio.run(callbacks["message"]["handle_translation"](bad_pair))
    cancel_message = RichFakeMessage(from_user=user)
    asyncio.run(callbacks["message"]["handle_cancel"](cancel_message))

    asyncio.run(
        callbacks["callback"]["handle_settings_notify_time"](
            notify_callback
        )
    )
    bad_time = RichFakeMessage(from_user=user, text="99:99")
    asyncio.run(callbacks["message"]["handle_translation"](bad_time))
    good_time = RichFakeMessage(from_user=user, text="08:45")
    asyncio.run(callbacks["message"]["handle_translation"](good_time))

    asyncio.run(
        callbacks["callback"]["handle_settings_timezone"](
            timezone_callback
        )
    )
    bad_timezone = RichFakeMessage(from_user=user, text="Nope/Zone")
    asyncio.run(callbacks["message"]["handle_translation"](bad_timezone))
    good_timezone = RichFakeMessage(
        from_user=user,
        text="Europe/Berlin",
    )
    asyncio.run(callbacks["message"]["handle_translation"](good_timezone))

    assert root_message.answers[0].text.startswith(
        "Send the pair as two language codes"
    )
    assert bad_pair.answers[0].text.startswith(
        "Send the pair as two language codes"
    )
    assert cancel_message.answers[0].text == "Settings input cancelled."
    assert root_message.answers[1].text.startswith(
        "Send the reminder time in HH:MM format."
    )
    assert bad_time.answers[0].text.startswith(
        "Send the reminder time as HH:MM."
    )
    assert "Reminder time: 08:45" in good_time.answers[0].text
    assert root_message.answers[2].text.startswith("Send an IANA timezone")
    assert bad_timezone.answers[0].text.startswith(
        "Send a valid IANA timezone name."
    )
    assert "Timezone: Europe/Berlin" in good_timezone.answers[0].text


def test_telegram_callback_edge_cases_cover_keep_reverse_and_toggle() -> None:
    test_container = build_test_container(
        datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
    )
    callbacks = callback_handlers(test_container)
    user = FakeUser(id=1)

    root_message = RichFakeMessage(from_user=user)
    keep_missing = FakeCallbackQuery(
        from_user=user,
        message=root_message,
        data="translation:keep",
    )
    asyncio.run(
        callbacks["callback"]["handle_translation_keep"](keep_missing)
    )

    reverse_message = RichFakeMessage(from_user=user)
    reverse_callback = FakeCallbackQuery(
        from_user=user,
        message=reverse_message,
        data="translation:reverse",
    )
    asyncio.run(
        callbacks["callback"]["handle_translation_reverse"](
            reverse_callback
        )
    )
    assert "Direction: Reverse" in reverse_message.answers[0].text

    translated = test_container.translate_phrase.execute(
        TranslatePhraseCommand(user_id=1, text="good luck")
    )
    pause_message = RichFakeMessage(from_user=user)
    pause_callback = FakeCallbackQuery(
        from_user=user,
        message=pause_message,
        data=f"card:pause:{translated.card_id}",
    )
    restore_message = RichFakeMessage(from_user=user)
    restore_callback = FakeCallbackQuery(
        from_user=user,
        message=restore_message,
        data=f"card:restore:{translated.card_id}",
    )
    invalid_pause = FakeCallbackQuery(
        from_user=user,
        message=RichFakeMessage(from_user=user),
        data="card:pause:not-a-uuid",
    )

    asyncio.run(callbacks["callback"]["handle_pause_card"](pause_callback))
    asyncio.run(
        callbacks["callback"]["handle_restore_card"](restore_callback)
    )
    asyncio.run(callbacks["callback"]["handle_pause_card"](invalid_pause))

    no_arg_pause = FakeMessage(from_user=FakeUser(id=1))
    bad_short = FakeMessage(from_user=FakeUser(id=1))
    asyncio.run(
        callbacks["message"]["handle_not_learning"](
            no_arg_pause,
            CommandObject(
                prefix="/",
                command="notlearning",
                mention=None,
                args="",
            ),
        )
    )
    asyncio.run(
        callbacks["message"]["handle_restore"](
            bad_short,
            CommandObject(
                prefix="/",
                command="restore",
                mention=None,
                args="deadbeef",
            ),
        )
    )

    assert keep_missing.acknowledgements == ["No pending phrase to save."]
    assert "was paused" in pause_message.answers[0].text
    assert "was restored" in restore_message.answers[0].text
    assert invalid_pause.message.answers[0].text == "Card id is invalid."
    assert no_arg_pause.answers == ["Usage: /notlearning <card_id|short_id>"]
    assert bad_short.answers == [
        "Card id was not found. Use /history to see recent short ids."
    ]


def test_telegram_quiz_empty_and_end_paths() -> None:
    test_container = build_test_container(
        datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
    )
    callbacks = callback_handlers(test_container)
    user = FakeUser(id=1)

    quiz_message = RichFakeMessage(from_user=user)
    asyncio.run(callbacks["message"]["handle_quiz"](quiz_message))
    assert quiz_message.answers[0].text.startswith("Nothing is due right now.")

    skip_message = FakeMessage(from_user=FakeUser(id=1))
    asyncio.run(callbacks["message"]["handle_skip"](skip_message))
    assert skip_message.answers == ["There is no active quiz session."]

    test_container.translate_phrase.execute(
        TranslatePhraseCommand(user_id=1, text="good luck")
    )
    test_container.clock.current = datetime(
        2026, 3, 30, 12, 0, tzinfo=timezone.utc
    )
    start_message = RichFakeMessage(from_user=user)
    asyncio.run(callbacks["message"]["handle_quiz"](start_message))
    intro_card = start_message.answers[0]

    continue_callback = FakeCallbackQuery(
        from_user=user,
        message=intro_card,
        data="quiz:continue",
    )
    asyncio.run(
        callbacks["callback"]["handle_quiz_continue"](
            continue_callback
        )
    )
    end_callback = FakeCallbackQuery(
        from_user=user,
        message=intro_card,
        data="quiz:end",
    )
    asyncio.run(callbacks["callback"]["handle_quiz_end"](end_callback))
    asyncio.run(callbacks["callback"]["handle_quiz_end"](end_callback))

    assert intro_card.answers[0].text.startswith("Quiz\n")
    assert (
        intro_card.answers[1].text == "Session ended. Due cards stay queued."
    )
    assert intro_card.answers[2].text.startswith("Progress\n")
    assert intro_card.answers[3].text == "There is no active quiz session."
