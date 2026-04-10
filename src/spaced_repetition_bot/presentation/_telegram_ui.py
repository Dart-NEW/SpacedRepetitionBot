"""Telegram formatting, parsing, and keyboard helpers."""

# UI helper map:
# - This module contains pure helpers only.
# - It does not call repositories or use cases directly.
# - Parsers normalize user-entered command arguments.
# - Formatters convert DTOs into Telegram-facing text blocks.
# - Keyboard builders keep callback payloads consistent.
# - Shared constants live here so router and flow stay aligned.
# - The warning card text is assembled separately from the main body.
# - Local datetime formatting is isolated for deterministic tests.
# - Direction labels stay centralized to avoid string drift.
# - Short id formatting is reused by history and toggle flows.
# - Reply keyboards are built here rather than inline in handlers.
# - Summary and dashboard keyboards also live here.
# - The command menu configuration belongs with UI constants.
# - Keeping these helpers pure makes them cheap to unit-test.
# - It also keeps the router focused on event wiring only.
# - Flow helpers import this module instead of duplicating strings.
# - When button labels change, update this file first.
# - When callback payloads change, update tests at the same time.
# - The public `presentation.telegram` module re-exports key helpers.
# - That preserves the old import surface while this file stays internal.

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram.types import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    MenuButtonCommands,
    ReplyKeyboardMarkup,
)

from spaced_repetition_bot.application.dtos import (
    ActiveQuizAnswerResult,
    HistoryItem,
    QuizSessionPrompt,
    QuizSessionStartResult,
    QuizSessionSummary,
    TranslatePhraseCommand,
    TranslationResult,
    UserProgressSnapshot,
    UserSettingsSnapshot,
)
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


@dataclass(slots=True)
class PendingTranslationPreview:
    """Transient translation preview waiting for explicit confirmation."""

    command: TranslatePhraseCommand


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
    ]
    if result.learning_status is None:
        body_lines.append("Learning: Not saved yet")
    else:
        body_lines.append(
            "Learning: "
            f"{_format_learning_status(result.learning_status)}"
        )
    if result.already_saved:
        body_lines.append("Status: Already in your deck")
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
    card_id: UUID | None,
    learning_status: LearningStatus | None,
    has_due_reviews: bool,
    show_warning_actions: bool,
) -> InlineKeyboardMarkup:
    keyboard = [_build_translation_primary_row(show_warning_actions)]
    action_row = _build_translation_action_row(
        card_id=card_id,
        learning_status=learning_status,
        has_due_reviews=has_due_reviews,
    )
    if action_row is not None:
        keyboard.append(action_row)
    warning_row = _build_translation_warning_row(show_warning_actions)
    if warning_row is not None:
        keyboard.append(warning_row)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def _build_translation_primary_row(
    show_warning_actions: bool,
) -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(
            text="Try reverse" if show_warning_actions else "Reverse",
            callback_data="translation:reverse",
        ),
        InlineKeyboardButton(
            text="Settings",
            callback_data=(
                "settings:pair" if show_warning_actions else "settings:open"
            ),
        ),
    ]


def _build_translation_action_row(
    *,
    card_id: UUID | None,
    learning_status: LearningStatus | None,
    has_due_reviews: bool,
) -> list[InlineKeyboardButton] | None:
    if card_id is not None and learning_status is not None:
        return _build_saved_translation_action_row(
            card_id=card_id,
            learning_status=learning_status,
            has_due_reviews=has_due_reviews,
        )
    if not has_due_reviews:
        return None
    return [_build_quiz_now_button()]


def _build_saved_translation_action_row(
    *,
    card_id: UUID,
    learning_status: LearningStatus,
    has_due_reviews: bool,
) -> list[InlineKeyboardButton]:
    row = [_build_learning_toggle_button(card_id, learning_status)]
    if has_due_reviews:
        row.append(_build_quiz_now_button())
    return row


def _build_learning_toggle_button(
    card_id: UUID,
    learning_status: LearningStatus,
) -> InlineKeyboardButton:
    is_paused = learning_status is LearningStatus.NOT_LEARNING
    action_text = "Restore" if is_paused else "Pause learning"
    action_name = "restore" if is_paused else "pause"
    return InlineKeyboardButton(
        text=action_text,
        callback_data=f"card:{action_name}:{card_id}",
    )


def _build_quiz_now_button() -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text="Quiz now",
        callback_data="quiz:continue",
    )


def _build_translation_warning_row(
    show_warning_actions: bool,
) -> list[InlineKeyboardButton] | None:
    if not show_warning_actions:
        return None
    return [
        InlineKeyboardButton(
            text="Keep anyway",
            callback_data="translation:keep",
        )
    ]


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


async def configure_telegram_bot_ui(bot) -> None:
    """Register command shortcuts and the commands menu in Telegram."""

    await bot.set_my_commands(list(BOT_COMMANDS))
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
