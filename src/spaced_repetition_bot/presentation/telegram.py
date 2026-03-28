"""aiogram presentation layer."""

from __future__ import annotations

from datetime import time
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message

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
)
from spaced_repetition_bot.bootstrap import ApplicationContainer
from spaced_repetition_bot.domain.enums import ReviewDirection


def build_telegram_router(container: ApplicationContainer) -> Router:
    """Build a minimal Telegram router for the MVP."""

    router = Router(name="spaced-repetition-bot")

    @router.message(CommandStart())
    async def handle_start(message: Message) -> None:
        if message.from_user is None:
            return
        await message.answer(
            (
                "Send me a phrase and I will translate it with your active language pair.\n"
                "Use /quiz for due reviews, /settings to inspect your defaults, "
                "and /direction forward|reverse to change the translation direction."
            )
        )

    @router.message(Command("history"))
    async def handle_history(message: Message) -> None:
        if message.from_user is None:
            return
        history = container.get_history.execute(GetHistoryQuery(user_id=message.from_user.id))
        if not history:
            await message.answer("History is empty.")
            return
        lines = [
            (
                f"{item.card_id} | {item.source_text} -> {item.translated_text} "
                f"| {item.learning_status}"
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
            "Cards: {total}, active: {active}, learned: {learned}, due: {due}".format(
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
        settings = container.get_settings.execute(GetSettingsQuery(user_id=message.from_user.id))
        await message.answer(
            (
                f"Pair: {settings.default_source_lang}/{settings.default_target_lang}\n"
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
            await message.answer("Usage: /pair <source_lang> <target_lang>")
            return
        await _update_settings(
            container=container,
            message=message,
            default_source_lang=args[0],
            default_target_lang=args[1],
        )

    @router.message(Command("direction"))
    async def handle_direction(message: Message, command: CommandObject) -> None:
        if message.from_user is None:
            return
        direction = _parse_direction(command.args)
        if direction is None:
            await message.answer("Usage: /direction <forward|reverse>")
            return
        await _update_settings(
            container=container,
            message=message,
            default_translation_direction=direction,
        )

    @router.message(Command("notifytime"))
    async def handle_notify_time(message: Message, command: CommandObject) -> None:
        if message.from_user is None:
            return
        parsed_time = _parse_notification_time(command.args)
        if parsed_time is None:
            await message.answer("Usage: /notifytime <HH:MM>")
            return
        await _update_settings(
            container=container,
            message=message,
            notification_time_local=parsed_time,
        )

    @router.message(Command("timezone"))
    async def handle_timezone(message: Message, command: CommandObject) -> None:
        if message.from_user is None:
            return
        timezone_name = (command.args or "").strip()
        if not timezone_name:
            await message.answer("Usage: /timezone <IANA timezone>")
            return
        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            await message.answer("Timezone must be a valid IANA timezone name.")
            return
        await _update_settings(
            container=container,
            message=message,
            timezone=timezone_name,
        )

    @router.message(Command("notifications"))
    async def handle_notifications(message: Message, command: CommandObject) -> None:
        if message.from_user is None:
            return
        raw_value = (command.args or "").strip().casefold()
        if raw_value not in {"on", "off"}:
            await message.answer("Usage: /notifications <on|off>")
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
            await message.answer("You have no due reviews right now.")
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
    async def handle_not_learning(message: Message, command: CommandObject) -> None:
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
        try:
            quiz_result = container.submit_active_quiz_answer.execute(
                user_id=message.from_user.id,
                answer_text=message.text,
            )
            answer_message = (
                f"Result: {quiz_result.review_result.outcome}\n"
                f"Expected: {quiz_result.review_result.expected_answer}\n"
                f"Next review: {quiz_result.review_result.next_review_at}\n"
                f"Learning status: {quiz_result.review_result.learning_status}"
            )
            await message.answer(answer_message)
            if quiz_result.next_prompt is not None:
                await message.answer(_format_quiz_prompt(quiz_result.next_prompt))
            return
        except QuizSessionNotFoundError:
            pass
        except ApplicationError as error:
            await message.answer(str(error))
            return
        try:
            result = container.translate_phrase.execute(
                TranslatePhraseCommand(
                    user_id=message.from_user.id,
                    text=message.text,
                )
            )
        except ApplicationError as error:
            await message.answer(str(error))
            return
        await message.answer(
            (
                f"{result.source_text} -> {result.translated_text}\n"
                f"Direction: {result.direction}\n"
                f"Pair: {result.source_lang}/{result.target_lang}\n"
                f"Learning status: {result.learning_status}"
            )
        )

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
    current = container.get_settings.execute(GetSettingsQuery(user_id=message.from_user.id))
    try:
        updated = container.update_settings.execute(
            UpdateSettingsCommand(
                user_id=message.from_user.id,
                default_source_lang=default_source_lang or current.default_source_lang,
                default_target_lang=default_target_lang or current.default_target_lang,
                default_translation_direction=(
                    default_translation_direction or current.default_translation_direction
                ),
                timezone=timezone or current.timezone,
                notification_time_local=notification_time_local or current.notification_time_local,
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
            f"Pair: {updated.default_source_lang}/{updated.default_target_lang}\n"
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
            f"Usage: /{'restore' if learning_enabled else 'notlearning'} <card_id>"
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
    await message.answer(f"{card.id} is now {action_label}. Current status: {card.learning_status}")


def _format_quiz_prompt(prompt) -> str:
    return (
        f"Quiz card: {prompt.card_id}\n"
        f"Direction: {prompt.direction}\n"
        f"Prompt: {prompt.prompt_text}\n"
        "Reply with your answer as plain text or use /skip to leave it due."
    )
