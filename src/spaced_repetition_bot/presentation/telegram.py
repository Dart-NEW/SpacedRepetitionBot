"""Compatibility exports for Telegram presentation helpers."""

from spaced_repetition_bot.presentation._telegram_router import (
    build_telegram_router,
)
from spaced_repetition_bot.presentation._telegram_ui import (
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
    configure_telegram_bot_ui,
)

__all__ = [
    "build_telegram_router",
    "configure_telegram_bot_ui",
    "_format_history_card",
    "_format_local_datetime",
    "_format_progress_card",
    "_format_quiz_intro",
    "_format_quiz_prompt",
    "_format_settings_card",
    "_format_summary",
    "_format_translation_card",
    "_parse_direction",
    "_parse_notification_time",
]
