"""aiogram presentation layer."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, time
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    MenuButtonCommands,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from spaced_repetition_bot.application.dtos import (
    ActiveQuizAnswerResult,
    GetHistoryQuery,
    GetSettingsQuery,
    GetUserProgressQuery,
    HistoryItem,
    QuizSessionPrompt,
    QuizSessionStartResult,
    QuizSessionSummary,
    SkipQuizResult,
    ToggleLearningCommand,
    TranslatePhraseCommand,
    TranslationResult,
    UpdateSettingsCommand,
    UserProgressSnapshot,
    UserSettingsSnapshot,
)
from spaced_repetition_bot.application.errors import (
    ApplicationError,
    InvalidSettingsError,
    QuizSessionNotFoundError,
    TranslationProviderError,
)
from spaced_repetition_bot.bootstrap import ApplicationContainer
from spaced_repetition_bot.domain.enums import (
    LearningStatus,
    ReviewDirection,
    ReviewOutcome,
)

START_TEXT = (
    "Send a word or short phrase and I will translate it with your "
    "current language pair.\n\n"
    "Recommended flow:\n"
    "1. Open /settings and choose your pair\n"
    "2. Send a phrase\n"
    "3. Tap the card buttons or use /quiz when reviews are due\n\n"
    "Use /help to see the available commands."
)

HELP_TEXT = (
    "Commands:\n"
    "/quiz - start or resume a review session\n"
    "/settings - open your current pair and reminder settings\n"
    "/progress - show your learning dashboard\n"
    "/history - show recent cards with short ids\n"
    "/pair <source_lang> <target_lang> - change the active pair\n"
    "/direction <forward|reverse> - switch the default direction\n"
    "/notifytime <HH:MM> - set the local reminder time\n"
    "/timezone <IANA timezone> - set your timezone\n"
    "/notifications <on|off> - enable or disable reminders\n"
    "/notlearning <card_id|short_id> - pause a saved card\n"
    "/restore <card_id|short_id> - restore a paused card\n"
    "/skip - leave the current quiz card due\n"
    "/cancel - leave the current settings input flow\n\n"
    "Tip: plain text translates the phrase and adds it to learning."
)

QUIZ_SKIP_TEXT = "Skip card"
QUIZ_END_TEXT = "End session"
SHORT_ID_LENGTH = 8
HISTORY_PAGE_SIZE = 10
SHORT_ID_LOOKUP_LIMIT = 200

BOT_COMMANDS: tuple[BotCommand, ...] = (
    BotCommand(command="help", description="Show quick help"),
    BotCommand(command="quiz", description="Review due cards"),
    BotCommand(command="settings", description="Open your settings"),
    BotCommand(command="progress", description="Show learning progress"),
    BotCommand(command="history", description="Show recent cards"),
    BotCommand(command="pair", description="Set active language pair"),
    BotCommand(command="direction", description="Set translation direction"),
    BotCommand(command="notifytime", description="Set reminder time"),
    BotCommand(command="timezone", description="Set timezone"),
    BotCommand(command="notifications", description="Toggle reminders"),
    BotCommand(command="cancel", description="Cancel settings input"),
)


@dataclass(slots=True)
class PendingInputState:
    """Transient Telegram UI state for guided settings input."""

    kind: str


def build_telegram_router(container: ApplicationContainer) -> Router:
    """Build the Telegram router with button-based UX."""

    router = Router(name="spaced-repetition-bot")
    pending_inputs: dict[int, PendingInputState] = {}

    @router.message(CommandStart())
    async def handle_start(message: Message) -> None:
        if message.from_user is None:
            return
        await message.answer(
            START_TEXT,
            reply_markup=_build_home_keyboard(has_due_reviews=False),
        )

    @router.message(Command("help"))
    async def handle_help(message: Message) -> None:
        if message.from_user is None:
            return
        await message.answer(HELP_TEXT)

    @router.message(Command("cancel"))
    async def handle_cancel(message: Message) -> None:
        if message.from_user is None:
            return
        pending_inputs.pop(message.from_user.id, None)
        await message.answer(
            "Settings input cancelled.",
            reply_markup=ReplyKeyboardRemove(),
        )

    @router.message(Command("history"))
    async def handle_history(message: Message) -> None:
        if message.from_user is None:
            return
        await _send_history_card(container, message)

    @router.message(Command("progress"))
    async def handle_progress(message: Message) -> None:
        if message.from_user is None:
            return
        await _send_progress_card(container, message)

    @router.message(Command("settings"))
    async def handle_settings(message: Message) -> None:
        if message.from_user is None:
            return
        await _send_settings_card(container, message)

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
        message: Message,
        command: CommandObject,
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
        message: Message,
        command: CommandObject,
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
        message: Message,
        command: CommandObject,
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
        if not _is_valid_timezone(timezone_name):
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
        message: Message,
        command: CommandObject,
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
        await _send_quiz_flow(container, message, activate=False)

    @router.message(Command("skip"))
    async def handle_skip(message: Message) -> None:
        if message.from_user is None:
            return
        await _skip_quiz_card(container, message)

    @router.message(Command("notlearning"))
    async def handle_not_learning(
        message: Message,
        command: CommandObject,
    ) -> None:
        await _toggle_learning_from_command(
            container=container,
            message=message,
            command=command,
            learning_enabled=False,
            action_label="paused",
        )

    @router.message(Command("restore"))
    async def handle_restore(
        message: Message,
        command: CommandObject,
    ) -> None:
        await _toggle_learning_from_command(
            container=container,
            message=message,
            command=command,
            learning_enabled=True,
            action_label="restored",
        )

    @router.callback_query(F.data == "quiz:start")
    async def handle_quiz_start(callback: CallbackQuery) -> None:
        await _handle_callback_quiz_start(
            container=container,
            callback=callback,
            activate_existing=True,
        )

    @router.callback_query(F.data == "quiz:continue")
    async def handle_quiz_continue(callback: CallbackQuery) -> None:
        await _handle_callback_quiz_start(
            container=container,
            callback=callback,
            activate_existing=False,
        )

    @router.callback_query(F.data == "quiz:end")
    async def handle_quiz_end(callback: CallbackQuery) -> None:
        await _handle_callback_quiz_end(container, callback)

    @router.callback_query(F.data == "settings:open")
    async def handle_settings_open(callback: CallbackQuery) -> None:
        await _handle_settings_open(container, callback)

    @router.callback_query(F.data == "settings:pair")
    async def handle_settings_pair(callback: CallbackQuery) -> None:
        await _begin_guided_settings_input(
            callback=callback,
            pending_inputs=pending_inputs,
            kind="pair",
            prompt=(
                "Send the pair as two language codes, for example:\n"
                "en es"
            ),
        )

    @router.callback_query(F.data == "settings:notifytime")
    async def handle_settings_notify_time(callback: CallbackQuery) -> None:
        await _begin_guided_settings_input(
            callback=callback,
            pending_inputs=pending_inputs,
            kind="notifytime",
            prompt=(
                "Send the reminder time in HH:MM format.\n"
                "Example: 09:30"
            ),
        )

    @router.callback_query(F.data == "settings:timezone")
    async def handle_settings_timezone(callback: CallbackQuery) -> None:
        await _begin_guided_settings_input(
            callback=callback,
            pending_inputs=pending_inputs,
            kind="timezone",
            prompt=(
                "Send an IANA timezone name.\n"
                "Example: Europe/Moscow"
            ),
        )

    @router.callback_query(F.data.startswith("settings:direction:"))
    async def handle_settings_direction(callback: CallbackQuery) -> None:
        if callback.from_user is None or callback.data is None:
            return
        direction = _parse_direction(callback.data.rsplit(":", maxsplit=1)[-1])
        await callback.answer()
        if direction is None or callback.message is None:
            return
        await _update_settings(
            container=container,
            message=callback.message,
            default_translation_direction=direction,
        )

    @router.callback_query(F.data.startswith("settings:notifications:"))
    async def handle_settings_notifications(
        callback: CallbackQuery,
    ) -> None:
        if callback.from_user is None or callback.data is None:
            return
        raw_value = callback.data.rsplit(":", maxsplit=1)[-1]
        await callback.answer()
        if callback.message is None:
            return
        await _update_settings(
            container=container,
            message=callback.message,
            notifications_enabled=raw_value == "on",
        )

    @router.callback_query(F.data == "dashboard:progress")
    async def handle_dashboard_progress(callback: CallbackQuery) -> None:
        if callback.message is None:
            return
        await callback.answer()
        await _send_progress_card(container, callback.message)

    @router.callback_query(F.data == "dashboard:history")
    async def handle_dashboard_history(callback: CallbackQuery) -> None:
        if callback.message is None:
            return
        await callback.answer()
        await _send_history_card(container, callback.message)

    @router.callback_query(F.data == "dashboard:translate")
    async def handle_dashboard_translate(callback: CallbackQuery) -> None:
        if callback.message is None:
            return
        await callback.answer()
        await callback.message.answer(
            "Send any word or phrase and I will translate it.",
            reply_markup=ReplyKeyboardRemove(),
        )

    @router.callback_query(F.data == "translation:reverse")
    async def handle_translation_reverse(callback: CallbackQuery) -> None:
        if callback.from_user is None or callback.message is None:
            return
        settings = container.get_settings.execute(
            GetSettingsQuery(user_id=callback.from_user.id)
        )
        next_direction = _reverse_direction(
            settings.default_translation_direction
        )
        await callback.answer()
        await _update_settings(
            container=container,
            message=callback.message,
            default_translation_direction=next_direction,
        )

    @router.callback_query(F.data == "translation:keep")
    async def handle_translation_keep(callback: CallbackQuery) -> None:
        if callback.message is None:
            return
        await callback.answer("Keeping the phrase in your current pair.")

    @router.callback_query(F.data.startswith("card:pause:"))
    async def handle_pause_card(callback: CallbackQuery) -> None:
        await _toggle_learning_from_callback(
            container=container,
            callback=callback,
            learning_enabled=False,
            action_label="paused",
        )

    @router.callback_query(F.data.startswith("card:restore:"))
    async def handle_restore_card(callback: CallbackQuery) -> None:
        await _toggle_learning_from_callback(
            container=container,
            callback=callback,
            learning_enabled=True,
            action_label="restored",
        )

    @router.message(F.text)
    async def handle_translation(message: Message) -> None:
        if message.from_user is None or message.text is None:
            return
        if message.text == QUIZ_SKIP_TEXT:
            await _skip_quiz_card(container, message)
            return
        if message.text == QUIZ_END_TEXT:
            await _end_quiz_session(container, message)
            return
        if await _try_handle_pending_input(
            container=container,
            message=message,
            pending_inputs=pending_inputs,
        ):
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


def _is_valid_timezone(timezone_name: str) -> bool:
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return False
    return True


def _safe_timezone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _format_direction(direction: ReviewDirection) -> str:
    if direction is ReviewDirection.FORWARD:
        return "Forward"
    return "Reverse"


def _reverse_direction(direction: ReviewDirection) -> ReviewDirection:
    if direction is ReviewDirection.FORWARD:
        return ReviewDirection.REVERSE
    return ReviewDirection.FORWARD


def _format_learning_status(status: LearningStatus) -> str:
    labels = {
        LearningStatus.ACTIVE: "Active",
        LearningStatus.LEARNED: "Learned",
        LearningStatus.NOT_LEARNING: "Paused",
    }
    return labels[status]


def _format_short_card_id(card_id: UUID) -> str:
    return str(card_id)[:SHORT_ID_LENGTH]


def _format_notification_state(enabled: bool) -> str:
    return "On" if enabled else "Off"


def _format_local_time(value: time) -> str:
    return value.strftime("%H:%M")


def _format_local_datetime(
    value: datetime | None,
    *,
    timezone_name: str,
    now: datetime,
) -> str:
    if value is None:
        return "Track completed"
    local_timezone = _safe_timezone(timezone_name)
    local_now = now.astimezone(local_timezone)
    local_value = value.astimezone(local_timezone)
    day_offset = (local_value.date() - local_now.date()).days
    if day_offset == 0:
        day_label = "today"
    elif day_offset == 1:
        day_label = "tomorrow"
    elif day_offset > 1:
        day_label = f"in {day_offset} days"
    else:
        return local_value.strftime("%Y-%m-%d at %H:%M")
    return f"{day_label} at {local_value:%H:%M}"


def _format_translation_card(
    result: TranslationResult,
    *,
    due_reviews_total: int,
) -> str:
    warning_lines = _build_warning_lines(result)
    body_lines = [
        "Translation",
        f"{result.source_text}",
        f"-> {result.translated_text}",
        "",
        f"Pair: {result.source_lang} -> {result.target_lang}",
        f"Direction: {_format_direction(result.direction)}",
        (
            "Learning: "
            f"{_format_learning_status(result.learning_status)}"
        ),
    ]
    if due_reviews_total > 0:
        body_lines.append(f"Due now: {due_reviews_total}")
    return "\n".join(warning_lines + body_lines)


def _build_warning_lines(result: TranslationResult) -> list[str]:
    if not result.has_pair_warning:
        return []
    lines = [
        "Pair warning",
        "This phrase may not match your active language pair.",
    ]
    if result.detected_source_lang is not None:
        lines.append(f"Detected source: {result.detected_source_lang}")
    if result.is_identity_translation:
        lines.append("The translated text matches the original input.")
    lines.append("")
    return lines


def _format_quiz_intro(start_result: QuizSessionStartResult) -> str:
    return (
        "Review session\n"
        f"Due now: {start_result.due_reviews_total}\n"
        f"Prompts in this round: {start_result.session_prompts_total}\n\n"
        "Tap Start to begin."
    )


def _format_quiz_prompt(prompt: QuizSessionPrompt) -> str:
    return (
        "Quiz\n"
        f"Progress: {prompt.session_position}/{prompt.total_prompts}\n"
        f"Direction: {_format_direction(prompt.direction)}\n"
        f"Prompt: {prompt.prompt_text}\n\n"
        "Type your answer below."
    )


def _format_quiz_feedback(
    result: ActiveQuizAnswerResult,
    *,
    timezone_name: str,
    now: datetime,
) -> str:
    outcome_label = (
        "Correct"
        if result.review_result.outcome is ReviewOutcome.CORRECT
        else "Not quite"
    )
    next_review = _format_local_datetime(
        result.review_result.next_review_at,
        timezone_name=timezone_name,
        now=now,
    )
    return (
        f"{outcome_label}\n"
        f"Expected: {result.review_result.expected_answer}\n"
        f"Next review: {next_review}\n"
        "Learning: "
        f"{_format_learning_status(result.review_result.learning_status)}"
    )


def _format_summary(summary: QuizSessionSummary) -> str:
    return (
        "Session complete\n"
        f"Answered: {summary.answered_prompts}/{summary.total_prompts}\n"
        f"Correct: {summary.correct_prompts}\n"
        f"Not quite: {summary.incorrect_prompts}\n"
        f"Still due: {summary.remaining_due_reviews}"
    )


def _format_settings_card(settings: UserSettingsSnapshot) -> str:
    return (
        "Settings\n"
        f"Pair: {settings.default_source_lang} -> "
        f"{settings.default_target_lang}\n"
        "Direction: "
        f"{_format_direction(settings.default_translation_direction)}\n"
        f"Timezone: {settings.timezone}\n"
        "Reminder time: "
        f"{_format_local_time(settings.notification_time_local)}\n"
        "Notifications: "
        f"{_format_notification_state(settings.notifications_enabled)}"
    )


def _format_progress_card(progress: UserProgressSnapshot) -> str:
    return (
        "Progress\n"
        f"Cards: {progress.total_cards}\n"
        f"Active: {progress.active_cards}\n"
        f"Learned: {progress.learned_cards}\n"
        f"Paused: {progress.not_learning_cards}\n"
        f"Due now: {progress.due_reviews}"
    )


def _format_history_card(history: list[HistoryItem]) -> str:
    if not history:
        return "History is empty."
    lines = ["Recent cards"]
    for item in history[:HISTORY_PAGE_SIZE]:
        lines.extend(
            [
                f"{_format_short_card_id(item.card_id)}  "
                f"{item.source_text} -> {item.translated_text}",
                "Learning: "
                f"{_format_learning_status(item.learning_status)}",
                "",
            ]
        )
    lines.append("Use /notlearning <id> or /restore <id> with a short id.")
    return "\n".join(lines).strip()


def _build_home_keyboard(
    *,
    has_due_reviews: bool,
) -> InlineKeyboardMarkup:
    primary = (
        InlineKeyboardButton(text="Quiz now", callback_data="quiz:continue")
        if has_due_reviews
        else InlineKeyboardButton(
            text="Progress",
            callback_data="dashboard:progress",
        )
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [primary],
            [
                InlineKeyboardButton(
                    text="History",
                    callback_data="dashboard:history",
                ),
                InlineKeyboardButton(
                    text="Settings",
                    callback_data="settings:open",
                ),
            ],
        ]
    )


def _build_translation_keyboard(
    *,
    card_id: UUID,
    learning_status: LearningStatus,
    has_due_reviews: bool,
    show_warning_actions: bool,
) -> InlineKeyboardMarkup:
    toggle_text = (
        "Restore"
        if learning_status is LearningStatus.NOT_LEARNING
        else "Pause learning"
    )
    toggle_prefix = (
        "card:restore:"
        if learning_status is LearningStatus.NOT_LEARNING
        else "card:pause:"
    )
    keyboard: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=(
                    "Try reverse"
                    if show_warning_actions
                    else "Reverse"
                ),
                callback_data="translation:reverse",
            ),
            InlineKeyboardButton(
                text="Settings",
                callback_data=(
                    (
                        "settings:pair"
                        if show_warning_actions
                        else "settings:open"
                    )
                ),
            ),
        ],
        [
            InlineKeyboardButton(
                text=toggle_text,
                callback_data=f"{toggle_prefix}{card_id}",
            ),
        ],
    ]
    if has_due_reviews:
        keyboard[1].append(
            InlineKeyboardButton(
                text="Quiz now",
                callback_data="quiz:continue",
            )
        )
    if show_warning_actions:
        keyboard.append(
            [
                InlineKeyboardButton(
                    text="Keep anyway",
                    callback_data="translation:keep",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def _build_quiz_intro_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Start quiz",
                    callback_data="quiz:start",
                ),
                InlineKeyboardButton(
                    text="End session",
                    callback_data="quiz:end",
                ),
            ]
        ]
    )


def _build_summary_keyboard(
    summary: QuizSessionSummary,
) -> InlineKeyboardMarkup:
    first_row: list[InlineKeyboardButton] = []
    if summary.remaining_due_reviews > 0:
        first_row.append(
            InlineKeyboardButton(
                text="Continue",
                callback_data="quiz:continue",
            )
        )
    first_row.append(
        InlineKeyboardButton(
            text="Progress",
            callback_data="dashboard:progress",
        )
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            first_row,
            [
                InlineKeyboardButton(
                    text="Translate",
                    callback_data="dashboard:translate",
                ),
                InlineKeyboardButton(
                    text="Settings",
                    callback_data="settings:open",
                ),
            ],
        ]
    )


def _build_settings_keyboard(
    settings: UserSettingsSnapshot,
) -> InlineKeyboardMarkup:
    next_direction = _reverse_direction(
        settings.default_translation_direction
    )
    next_notifications = (
        "off" if settings.notifications_enabled else "on"
    )
    notification_label = (
        "Turn off reminders"
        if settings.notifications_enabled
        else "Turn on reminders"
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Change pair",
                    callback_data="settings:pair",
                ),
                InlineKeyboardButton(
                    text=(
                        "Direction: "
                        f"{_format_direction(next_direction)}"
                    ),
                    callback_data=(
                        "settings:direction:"
                        f"{next_direction.value}"
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Reminder time",
                    callback_data="settings:notifytime",
                ),
                InlineKeyboardButton(
                    text="Timezone",
                    callback_data="settings:timezone",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=notification_label,
                    callback_data=(
                        "settings:notifications:"
                        f"{next_notifications}"
                    ),
                )
            ],
        ]
    )


def _build_quiz_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=QUIZ_SKIP_TEXT),
                KeyboardButton(text=QUIZ_END_TEXT),
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Type your answer",
    )


async def _send_history_card(
    container: ApplicationContainer,
    message: Message,
) -> None:
    if message.from_user is None:
        return
    history = container.get_history.execute(
        GetHistoryQuery(
            user_id=message.from_user.id,
            limit=HISTORY_PAGE_SIZE,
        )
    )
    await message.answer(_format_history_card(history))


async def _send_progress_card(
    container: ApplicationContainer,
    message: Message,
) -> None:
    if message.from_user is None:
        return
    progress = container.get_user_progress.execute(
        GetUserProgressQuery(user_id=message.from_user.id)
    )
    await message.answer(
        _format_progress_card(progress),
        reply_markup=_build_home_keyboard(
            has_due_reviews=progress.due_reviews > 0
        ),
    )


async def _send_settings_card(
    container: ApplicationContainer,
    message: Message,
) -> None:
    if message.from_user is None:
        return
    settings = container.get_settings.execute(
        GetSettingsQuery(user_id=message.from_user.id)
    )
    await message.answer(
        _format_settings_card(settings),
        reply_markup=_build_settings_keyboard(settings),
    )


async def _send_quiz_flow(
    container: ApplicationContainer,
    message: Message,
    *,
    activate: bool,
) -> None:
    if message.from_user is None:
        return
    start_result = container.start_quiz_session.execute(
        message.from_user.id,
        activate=activate,
    )
    if start_result is None:
        await message.answer(
            "Nothing is due right now. Send a new phrase or check your "
            "progress.",
            reply_markup=_build_home_keyboard(has_due_reviews=False),
        )
        return
    if start_result.awaiting_start:
        await message.answer(
            _format_quiz_intro(start_result),
            reply_markup=_build_quiz_intro_keyboard(),
        )
        return
    prompt_message = await message.answer(
        _format_quiz_prompt(start_result.prompt),
        reply_markup=_build_quiz_reply_keyboard(),
    )
    await _store_quiz_message_id(
        container=container,
        user_id=message.from_user.id,
        message_id=getattr(prompt_message, "message_id", None),
    )


async def _store_quiz_message_id(
    container: ApplicationContainer,
    *,
    user_id: int,
    message_id: int | None,
) -> None:
    if message_id is None:
        return
    container.start_quiz_session.execute(user_id, message_id=message_id)


async def _handle_callback_quiz_start(
    container: ApplicationContainer,
    callback: CallbackQuery,
    *,
    activate_existing: bool,
) -> None:
    if callback.from_user is None or callback.message is None:
        return
    await callback.answer()
    if activate_existing:
        start_result = container.start_quiz_session.execute(
            callback.from_user.id,
            activate=True,
        )
    else:
        start_result = container.start_quiz_session.execute(
            callback.from_user.id,
            activate=True,
        )
    if start_result is None:
        await callback.message.answer(
            "Nothing is due right now.",
            reply_markup=_build_home_keyboard(has_due_reviews=False),
        )
        return
    prompt_message = await callback.message.answer(
        _format_quiz_prompt(start_result.prompt),
        reply_markup=_build_quiz_reply_keyboard(),
    )
    await _store_quiz_message_id(
        container=container,
        user_id=callback.from_user.id,
        message_id=getattr(prompt_message, "message_id", None),
    )


async def _handle_callback_quiz_end(
    container: ApplicationContainer,
    callback: CallbackQuery,
) -> None:
    if callback.message is None:
        return
    await callback.answer()
    await _end_quiz_session(container, callback.message)


async def _handle_settings_open(
    container: ApplicationContainer,
    callback: CallbackQuery,
) -> None:
    if callback.message is None:
        return
    await callback.answer()
    await _send_settings_card(container, callback.message)


async def _begin_guided_settings_input(
    *,
    callback: CallbackQuery,
    pending_inputs: dict[int, PendingInputState],
    kind: str,
    prompt: str,
) -> None:
    if callback.from_user is None or callback.message is None:
        return
    pending_inputs[callback.from_user.id] = PendingInputState(kind=kind)
    await callback.answer()
    await callback.message.answer(prompt)


async def _try_handle_pending_input(
    *,
    container: ApplicationContainer,
    message: Message,
    pending_inputs: dict[int, PendingInputState],
) -> bool:
    if message.from_user is None or message.text is None:
        return False
    state = pending_inputs.get(message.from_user.id)
    if state is None:
        return False
    handled = await _handle_pending_input(
        container=container,
        message=message,
        state=state,
    )
    if handled:
        pending_inputs.pop(message.from_user.id, None)
    return True


async def _handle_pending_input(
    *,
    container: ApplicationContainer,
    message: Message,
    state: PendingInputState,
) -> bool:
    if state.kind == "pair":
        return await _handle_pair_input(container, message)
    if state.kind == "notifytime":
        return await _handle_notify_time_input(container, message)
    if state.kind == "timezone":
        return await _handle_timezone_input(container, message)
    await message.answer("This input flow is no longer active.")
    return True


async def _handle_pair_input(
    container: ApplicationContainer,
    message: Message,
) -> bool:
    if message.text is None:
        return False
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer(
            "Send the pair as two language codes, for example: en es\n"
            "Use /cancel to stop."
        )
        return False
    await _update_settings(
        container=container,
        message=message,
        default_source_lang=parts[0],
        default_target_lang=parts[1],
    )
    return True


async def _handle_notify_time_input(
    container: ApplicationContainer,
    message: Message,
) -> bool:
    parsed_time = _parse_notification_time(message.text)
    if parsed_time is None:
        await message.answer(
            "Send the reminder time as HH:MM.\nUse /cancel to stop."
        )
        return False
    await _update_settings(
        container=container,
        message=message,
        notification_time_local=parsed_time,
    )
    return True


async def _handle_timezone_input(
    container: ApplicationContainer,
    message: Message,
) -> bool:
    timezone_name = (message.text or "").strip()
    if not timezone_name or not _is_valid_timezone(timezone_name):
        await message.answer(
            "Send a valid IANA timezone name.\nUse /cancel to stop."
        )
        return False
    await _update_settings(
        container=container,
        message=message,
        timezone=timezone_name,
    )
    return True


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
                default_source_lang=(
                    default_source_lang or current.default_source_lang
                ),
                default_target_lang=(
                    default_target_lang or current.default_target_lang
                ),
                default_translation_direction=(
                    default_translation_direction
                    or current.default_translation_direction
                ),
                timezone=timezone or current.timezone,
                notification_time_local=(
                    notification_time_local
                    or current.notification_time_local
                ),
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
        _format_settings_card(updated),
        reply_markup=_build_settings_keyboard(updated),
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
        command_name = "restore" if learning_enabled else "notlearning"
        await message.answer(
            f"Usage: /{command_name} <card_id|short_id>"
        )
        return
    card_id = _resolve_card_reference(
        container=container,
        user_id=message.from_user.id,
        raw_card_id=raw_card_id,
    )
    if card_id is None:
        await message.answer(
            "Card id was not found. Use /history to see recent short ids."
        )
        return
    await _toggle_learning_by_id(
        container=container,
        message=message,
        card_id=card_id,
        learning_enabled=learning_enabled,
        action_label=action_label,
    )


def _resolve_card_reference(
    *,
    container: ApplicationContainer,
    user_id: int,
    raw_card_id: str,
) -> UUID | None:
    try:
        return UUID(raw_card_id)
    except ValueError:
        pass
    short_id = raw_card_id.casefold()
    history = container.get_history.execute(
        GetHistoryQuery(user_id=user_id, limit=SHORT_ID_LOOKUP_LIMIT)
    )
    matches = [
        item.card_id
        for item in history
        if _format_short_card_id(item.card_id).casefold() == short_id
    ]
    if len(matches) != 1:
        return None
    return matches[0]


async def _toggle_learning_from_callback(
    container: ApplicationContainer,
    callback: CallbackQuery,
    *,
    learning_enabled: bool,
    action_label: str,
) -> None:
    if callback.data is None or callback.message is None:
        return
    await callback.answer()
    raw_card_id = callback.data.rsplit(":", maxsplit=1)[-1]
    try:
        card_id = UUID(raw_card_id)
    except ValueError:
        await callback.message.answer("Card id is invalid.")
        return
    await _toggle_learning_by_id(
        container=container,
        message=callback.message,
        card_id=card_id,
        learning_enabled=learning_enabled,
        action_label=action_label,
    )


async def _toggle_learning_by_id(
    *,
    container: ApplicationContainer,
    message: Message,
    card_id: UUID,
    learning_enabled: bool,
    action_label: str,
) -> None:
    if message.from_user is None:
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
        f"{_format_short_card_id(card.id)} was {action_label}.\n"
        "Learning: "
        f"{_format_learning_status(card.learning_status)}"
    )


async def _skip_quiz_card(
    container: ApplicationContainer,
    message: Message,
) -> None:
    if message.from_user is None:
        return
    skipped = container.skip_quiz_session.execute(message.from_user.id)
    if skipped is None:
        await message.answer("There is no active quiz session.")
        return
    await _send_skip_result(container, message, skipped)


async def _send_skip_result(
    container: ApplicationContainer,
    message: Message,
    skipped: SkipQuizResult,
) -> None:
    await message.answer("Card skipped. It stays due.")
    if skipped.next_prompt is not None:
        prompt_message = await message.answer(
            _format_quiz_prompt(skipped.next_prompt),
            reply_markup=_build_quiz_reply_keyboard(),
        )
        if message.from_user is not None:
            await _store_quiz_message_id(
                container=container,
                user_id=message.from_user.id,
                message_id=getattr(prompt_message, "message_id", None),
            )
        return
    if skipped.session_summary is not None:
        await _send_session_summary(message, skipped.session_summary)


async def _end_quiz_session(
    container: ApplicationContainer,
    message: Message,
) -> None:
    if message.from_user is None:
        return
    ended = container.end_quiz_session.execute(message.from_user.id)
    if not ended:
        await message.answer("There is no active quiz session.")
        return
    await message.answer(
        "Session ended. Due cards stay queued.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await _send_progress_card(container, message)


async def _try_handle_quiz_answer(
    container: ApplicationContainer,
    message: Message,
) -> bool:
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
    await _send_quiz_result(container, message, quiz_result)
    return True


async def _send_quiz_result(
    container: ApplicationContainer,
    message: Message,
    quiz_result: ActiveQuizAnswerResult,
) -> None:
    if message.from_user is None:
        return
    settings = container.get_settings.execute(
        GetSettingsQuery(user_id=message.from_user.id)
    )
    await message.answer(
        _format_quiz_feedback(
            quiz_result,
            timezone_name=settings.timezone,
            now=container.clock.now(),
        )
    )
    if quiz_result.next_prompt is not None:
        prompt_message = await message.answer(
            _format_quiz_prompt(quiz_result.next_prompt),
            reply_markup=_build_quiz_reply_keyboard(),
        )
        await _store_quiz_message_id(
            container=container,
            user_id=message.from_user.id,
            message_id=getattr(prompt_message, "message_id", None),
        )
        return
    if quiz_result.session_summary is not None:
        await _send_session_summary(message, quiz_result.session_summary)


async def _send_session_summary(
    message: Message,
    summary: QuizSessionSummary,
) -> None:
    await message.answer(
        "Review round finished.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer(
        _format_summary(summary),
        reply_markup=_build_summary_keyboard(summary),
    )


async def _handle_translation_request(
    container: ApplicationContainer,
    message: Message,
) -> None:
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
    due_reviews = container.get_due_reviews.execute(message.from_user.id)
    await message.answer(
        _format_translation_card(
            result,
            due_reviews_total=len(due_reviews),
        ),
        reply_markup=_build_translation_keyboard(
            card_id=result.card_id,
            learning_status=result.learning_status,
            has_due_reviews=bool(due_reviews),
            show_warning_actions=result.has_pair_warning,
        ),
    )


async def configure_telegram_bot_ui(bot) -> None:
    """Register command shortcuts and the commands menu in Telegram."""

    await bot.set_my_commands(list(BOT_COMMANDS))
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
