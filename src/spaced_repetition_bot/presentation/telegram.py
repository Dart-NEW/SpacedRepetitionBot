"""aiogram presentation layer."""

from __future__ import annotations

import asyncio
from datetime import time
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import BotCommand, MenuButtonCommands, Message

from spaced_repetition_bot.application.dtos import (
    GetHistoryQuery,
    GetSettingsQuery,
    GetUserProgressQuery,
    ToggleLearningCommand,
    TranslatePhraseCommand,
    UpdateSettingsCommand,
)
from spaced_repetition_bot.application.errors import (
    ApplicationError,
    InvalidSettingsError,
    QuizSessionNotFoundError,
    TranslationProviderError,
)
from spaced_repetition_bot.bootstrap import ApplicationContainer
from spaced_repetition_bot.domain.enums import ReviewDirection

START_TEXT = (
    "Send a word or phrase and I will translate it using your current "
    "language pair.\n\n"
    "Quick start:\n"
    "1. /pair en es\n"
    "2. Send a phrase like good luck\n"
    "3. Use /quiz when reviews are due\n\n"
    "Use /help to see all commands."
)

HELP_TEXT = (
    "Commands:\n"
    "/quiz - review due cards\n"
    "/settings - show your current pair and reminder settings\n"
    "/progress - show how many cards are active, learned, and due\n"
    "/history - show recent cards with ids for /notlearning or /restore\n"
    "/pair <source_lang> <target_lang> - change the active pair\n"
    "/direction <forward|reverse> - switch the default direction\n"
    "/notifytime <HH:MM> - set the local reminder time\n"
    "/timezone <IANA timezone> - set your timezone\n"
    "/notifications <on|off> - enable or disable reminders\n"
    "/skip - leave the current quiz card due\n\n"
    "Tip: plain text translates the phrase and adds it to learning."
)

BOT_COMMANDS: tuple[BotCommand, ...] = (
    BotCommand(command="help", description="Show quick help"),
    BotCommand(command="quiz", description="Review due cards"),
    BotCommand(command="settings", description="Show current settings"),
    BotCommand(command="progress", description="Show learning progress"),
    BotCommand(command="history", description="Show recent cards"),
    BotCommand(command="pair", description="Set active language pair"),
    BotCommand(command="direction", description="Set review direction"),
    BotCommand(command="notifytime", description="Set reminder time"),
    BotCommand(command="timezone", description="Set your timezone"),
    BotCommand(command="notifications", description="Toggle reminders"),
)


def build_telegram_router(container: ApplicationContainer) -> Router:
    """Build a minimal Telegram router for the MVP."""

    router = Router(name="spaced-repetition-bot")

    @router.message(CommandStart())
    async def handle_start(message: Message) -> None:
        if message.from_user is None:
            return
        await message.answer(START_TEXT)

    @router.message(Command("help"))
    async def handle_help(message: Message) -> None:
        if message.from_user is None:
            return
        await message.answer(HELP_TEXT)

    @router.message(Command("history"))
    async def handle_history(message: Message) -> None:
        if message.from_user is None:
            return
        history = container.get_history.execute(
            GetHistoryQuery(user_id=message.from_user.id)
        )
        if not history:
            await message.answer("History is empty.")
            return
        lines = [
            (
                f"{item.card_id}\n"
                f"{item.source_text} -> {item.translated_text}\n"
                f"Status: {item.learning_status}"
            )
            for item in history[:10]
        ]
        await message.answer("\n".join(lines))

    @router.message(Command("progress"))
    async def handle_progress(message: Message) -> None:
        if message.from_user is None:
            return
        progress = container.get_user_progress.execute(
            GetUserProgressQuery(user_id=message.from_user.id)
        )
        await message.answer(
            (
                "Cards: {total}, active: {active}, "
                "learned: {learned}, due: {due}"
            ).format(
                total=progress.total_cards,
                active=progress.active_cards,
                learned=progress.learned_cards,
                due=progress.due_reviews,
            )
        )

    @router.message(Command("settings"))
    async def handle_settings(message: Message) -> None:
        if message.from_user is None:
            return
        settings = container.get_settings.execute(
            GetSettingsQuery(user_id=message.from_user.id)
        )
        await message.answer(
            (
                "Pair: "
                f"{settings.default_source_lang}/"
                f"{settings.default_target_lang}\n"
                f"Direction: {settings.default_translation_direction}\n"
                f"Timezone: {settings.timezone}\n"
                f"Notify time: {settings.notification_time_local}\n"
                f"Notifications: {settings.notifications_enabled}"
            )
        )

    @router.message(Command("pair"))
    async def handle_pair(message: Message, command: CommandObject) -> None:
        if message.from_user is None:
            return
        args = (command.args or "").split()
        if len(args) != 2:
            await message.answer(
                "Usage: /pair <source_lang> <target_lang>\n"
                "Example: /pair en es"
            )
            return
        await _update_settings(
            container=container,
            message=message,
            default_source_lang=args[0],
            default_target_lang=args[1],
        )

    @router.message(Command("direction"))
    async def handle_direction(
        message: Message, command: CommandObject
    ) -> None:
        if message.from_user is None:
            return
        direction = _parse_direction(command.args)
        if direction is None:
            await message.answer(
                "Usage: /direction <forward|reverse>\n"
                "Example: /direction reverse"
            )
            return
        await _update_settings(
            container=container,
            message=message,
            default_translation_direction=direction,
        )

    @router.message(Command("notifytime"))
    async def handle_notify_time(
        message: Message, command: CommandObject
    ) -> None:
        if message.from_user is None:
            return
        parsed_time = _parse_notification_time(command.args)
        if parsed_time is None:
            await message.answer(
                "Usage: /notifytime <HH:MM>\n"
                "Example: /notifytime 09:30"
            )
            return
        await _update_settings(
            container=container,
            message=message,
            notification_time_local=parsed_time,
        )

    @router.message(Command("timezone"))
    async def handle_timezone(
        message: Message, command: CommandObject
    ) -> None:
        if message.from_user is None:
            return
        timezone_name = (command.args or "").strip()
        if not timezone_name:
            await message.answer(
                "Usage: /timezone <IANA timezone>\n"
                "Example: /timezone Europe/Moscow"
            )
            return
        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            await message.answer(
                "Timezone must be a valid IANA timezone name."
            )
            return
        await _update_settings(
            container=container,
            message=message,
            timezone=timezone_name,
        )

    @router.message(Command("notifications"))
    async def handle_notifications(
        message: Message, command: CommandObject
    ) -> None:
        if message.from_user is None:
            return
        raw_value = (command.args or "").strip().casefold()
        if raw_value not in {"on", "off"}:
            await message.answer(
                "Usage: /notifications <on|off>\n"
                "Example: /notifications off"
            )
            return
        await _update_settings(
            container=container,
            message=message,
            notifications_enabled=raw_value == "on",
        )

    @router.message(Command("quiz"))
    async def handle_quiz(message: Message) -> None:
        if message.from_user is None:
            return
        prompt = container.start_quiz_session.execute(message.from_user.id)
        if prompt is None:
            await message.answer(
                "You have no due reviews right now. Send a new phrase or "
                "check /progress."
            )
            return
        await message.answer(_format_quiz_prompt(prompt))

    @router.message(Command("skip"))
    async def handle_skip(message: Message) -> None:
        if message.from_user is None:
            return
        skipped = container.skip_quiz_session.execute(message.from_user.id)
        if skipped:
            await message.answer("Quiz session skipped. The card remains due.")
            return
        await message.answer("There is no active quiz session.")

    @router.message(Command("notlearning"))
    async def handle_not_learning(
        message: Message, command: CommandObject
    ) -> None:
        await _toggle_learning_from_command(
            container=container,
            message=message,
            command=command,
            learning_enabled=False,
            action_label="excluded from learning",
        )

    @router.message(Command("restore"))
    async def handle_restore(message: Message, command: CommandObject) -> None:
        await _toggle_learning_from_command(
            container=container,
            message=message,
            command=command,
            learning_enabled=True,
            action_label="restored to learning",
        )

    @router.message(F.text)
    async def handle_translation(message: Message) -> None:
        if message.from_user is None or message.text is None:
            return
        if await _try_handle_quiz_answer(container, message):
            return
        await _handle_translation_request(container, message)

    return router


def _parse_direction(raw_value: str | None) -> ReviewDirection | None:
    raw_value = (raw_value or "").strip().casefold()
    if raw_value == ReviewDirection.FORWARD.value:
        return ReviewDirection.FORWARD
    if raw_value == ReviewDirection.REVERSE.value:
        return ReviewDirection.REVERSE
    return None


def _parse_notification_time(raw_value: str | None) -> time | None:
    parts = (raw_value or "").strip().split(":")
    if len(parts) != 2:
        return None
    try:
        hours = int(parts[0])
        minutes = int(parts[1])
    except ValueError:
        return None
    if not (0 <= hours <= 23 and 0 <= minutes <= 59):
        return None
    return time(hour=hours, minute=minutes)


async def _update_settings(
    container: ApplicationContainer,
    message: Message,
    *,
    default_source_lang: str | None = None,
    default_target_lang: str | None = None,
    default_translation_direction: ReviewDirection | None = None,
    timezone: str | None = None,
    notification_time_local: time | None = None,
    notifications_enabled: bool | None = None,
) -> None:
    if message.from_user is None:
        return
    current = container.get_settings.execute(
        GetSettingsQuery(user_id=message.from_user.id)
    )
    try:
        updated = container.update_settings.execute(
            UpdateSettingsCommand(
                user_id=message.from_user.id,
                default_source_lang=default_source_lang
                or current.default_source_lang,
                default_target_lang=default_target_lang
                or current.default_target_lang,
                default_translation_direction=(
                    default_translation_direction
                    or current.default_translation_direction
                ),
                timezone=timezone or current.timezone,
                notification_time_local=notification_time_local
                or current.notification_time_local,
                notifications_enabled=(
                    current.notifications_enabled
                    if notifications_enabled is None
                    else notifications_enabled
                ),
            )
        )
    except InvalidSettingsError as error:
        await message.answer(str(error))
        return
    await message.answer(
        (
            "Settings updated.\n"
            "Pair: "
            f"{updated.default_source_lang}/"
            f"{updated.default_target_lang}\n"
            f"Direction: {updated.default_translation_direction}\n"
            f"Timezone: {updated.timezone}\n"
            f"Notify time: {updated.notification_time_local}\n"
            f"Notifications: {updated.notifications_enabled}"
        )
    )


async def _toggle_learning_from_command(
    container: ApplicationContainer,
    message: Message,
    command: CommandObject,
    *,
    learning_enabled: bool,
    action_label: str,
) -> None:
    if message.from_user is None:
        return
    raw_card_id = (command.args or "").strip()
    if not raw_card_id:
        await message.answer(
            "Usage: "
            f"/{'restore' if learning_enabled else 'notlearning'} "
            "<card_id>"
        )
        return
    try:
        card_id = UUID(raw_card_id)
    except ValueError:
        await message.answer("Card id must be a valid UUID.")
        return
    try:
        card = container.toggle_learning.execute(
            ToggleLearningCommand(
                user_id=message.from_user.id,
                card_id=card_id,
                learning_enabled=learning_enabled,
            )
        )
    except ApplicationError as error:
        await message.answer(str(error))
        return
    await message.answer(
        f"{card.id} is now {action_label}. "
        f"Current status: {card.learning_status}"
    )


async def _try_handle_quiz_answer(
    container: ApplicationContainer, message: Message
) -> bool:
    """Handle the message as a quiz answer when a session is active."""

    if message.from_user is None or message.text is None:
        return False
    try:
        quiz_result = container.submit_active_quiz_answer.execute(
            user_id=message.from_user.id,
            answer_text=message.text,
        )
    except QuizSessionNotFoundError:
        return False
    except ApplicationError as error:
        await message.answer(str(error))
        return True

    await message.answer(_format_quiz_answer_message(quiz_result))
    if quiz_result.next_prompt is not None:
        await message.answer(_format_quiz_prompt(quiz_result.next_prompt))
    return True


async def _handle_translation_request(
    container: ApplicationContainer, message: Message
) -> None:
    """Translate plain text when there is no active quiz session."""

    if message.from_user is None or message.text is None:
        return
    try:
        result = await asyncio.to_thread(
            container.translate_phrase.execute,
            TranslatePhraseCommand(
                user_id=message.from_user.id,
                text=message.text,
            ),
        )
    except TranslationProviderError:
        await message.answer("Translation provider is unavailable right now.")
        return
    except ApplicationError as error:
        await message.answer(str(error))
        return

    await message.answer(_format_translation_result_message(result))


def _format_quiz_answer_message(quiz_result) -> str:
    """Build a compact quiz answer response for Telegram."""

    outcome_label = (
        "Correct"
        if quiz_result.review_result.outcome.value == "correct"
        else "Incorrect"
    )
    next_review = (
        str(quiz_result.review_result.next_review_at)
        if quiz_result.review_result.next_review_at is not None
        else "Track completed"
    )
    return (
        f"Result: {outcome_label}\n"
        f"Expected: {quiz_result.review_result.expected_answer}\n"
        f"Next review: {next_review}\n"
        f"Learning status: {quiz_result.review_result.learning_status}"
    )


def _format_translation_result_message(result) -> str:
    """Build a compact translation response for Telegram."""

    return (
        f"{result.source_text} -> {result.translated_text}\n"
        f"Direction: {result.direction}\n"
        f"Pair: {result.source_lang}/{result.target_lang}\n"
        f"Learning status: {result.learning_status}"
    )


def _format_quiz_prompt(prompt) -> str:
    return (
        "Quiz\n"
        f"Direction: {prompt.direction}\n"
        f"Prompt: {prompt.prompt_text}\n"
        "Reply with your answer as plain text or use /skip to leave it due."
    )


async def configure_telegram_bot_ui(bot) -> None:
    """Register command shortcuts and the commands menu in Telegram."""

    await bot.set_my_commands(list(BOT_COMMANDS))
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
