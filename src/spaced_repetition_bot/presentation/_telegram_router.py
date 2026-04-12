"""Telegram router construction."""

# Router notes:
# - This module is responsible only for aiogram event registration.
# - It wires Telegram commands, callbacks, and plain-text handlers.
# - The nested handler names are kept stable for the existing tests.
# - Shared transient dictionaries are scoped to one router instance.
# - Pending guided input state is keyed by Telegram user id.
# - Pending warning previews are also keyed by Telegram user id.
# - Router handlers validate the most obvious command syntax locally.
# - After that, they delegate real work to flow helpers.
# - Callback handlers primarily unpack payloads and route execution.
# - Message handlers decide whether text is a command-like UI action,
# - a guided settings reply, a quiz answer, or a translation request.
# - The module does not format cards or build keyboards directly.
# - It also does not own business rules or persistence details.
# - Those concerns stay in `_telegram_flow` and application use cases.
# - Keeping routing separate makes chat behavior easier to scan.
# - It also keeps callback naming and registration centralized.
# - The compatibility facade in `presentation.telegram` re-exports
# - `build_telegram_router` so existing imports continue to work.
# - If new commands are added, this module should change first.
# - If command text changes, `_telegram_ui` should usually change too.

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from spaced_repetition_bot.application.dtos import (
    GetSettingsQuery,
    TranslatePhraseCommand,
)
from spaced_repetition_bot.bootstrap import ApplicationContainer
from spaced_repetition_bot.domain.enums import ReviewDirection
from spaced_repetition_bot.presentation._telegram_flow import (
    _begin_guided_settings_input,
    _end_quiz_session,
    _handle_callback_quiz_end,
    _handle_callback_quiz_start,
    _handle_settings_open,
    _handle_translation_request,
    _send_history_card,
    _send_progress_card,
    _send_quiz_flow,
    _send_settings_card,
    _skip_quiz_card,
    _toggle_learning_from_callback,
    _toggle_learning_from_command,
    _try_handle_pending_input,
    _try_handle_quiz_answer,
    _update_settings,
)
from spaced_repetition_bot.presentation._telegram_ui import (
    HELP_TEXT,
    QUIZ_END_TEXT,
    QUIZ_SKIP_TEXT,
    START_TEXT,
    PendingInputState,
    PendingTranslationPreview,
    _build_home_keyboard,
    _is_valid_timezone,
    _parse_direction,
    _parse_notification_frequency_days,
    _parse_notification_time,
    _reverse_direction,
)


def build_telegram_router(container: ApplicationContainer) -> Router:
    """Build the Telegram router with button-based UX."""

    router = Router(name="spaced-repetition-bot")
    pending_inputs: dict[int, PendingInputState] = {}
    pending_previews: dict[int, PendingTranslationPreview] = {}

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
        pending_previews.pop(message.from_user.id, None)
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

    @router.message(Command("notifyevery"))
    async def handle_notify_every(
        message: Message,
        command: CommandObject,
    ) -> None:
        if message.from_user is None:
            return
        notification_frequency_days = _parse_notification_frequency_days(
            command.args
        )
        if notification_frequency_days is None:
            await message.answer(
                "Usage: /notifyevery <days>\n"
                "Example: /notifyevery 2"
            )
            return
        await _update_settings(
            container=container,
            message=message,
            notification_frequency_days=notification_frequency_days,
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

    @router.callback_query(F.data == "settings:notifyevery")
    async def handle_settings_notify_every(
        callback: CallbackQuery,
    ) -> None:
        await _begin_guided_settings_input(
            callback=callback,
            pending_inputs=pending_inputs,
            kind="notifyevery",
            prompt=(
                "Send the reminder frequency in whole days.\n"
                "Example: 2"
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
        direction = _parse_direction(
            callback.data.rsplit(":", maxsplit=1)[-1]
        )
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
        preview = pending_previews.get(callback.from_user.id)
        if preview is not None:
            await callback.answer()
            reversed_direction = _reverse_direction(
                preview.command.direction or ReviewDirection.FORWARD
            )
            await _handle_translation_request(
                container=container,
                message=callback.message,
                pending_previews=pending_previews,
                command=TranslatePhraseCommand(
                    user_id=callback.from_user.id,
                    text=preview.command.text,
                    direction=reversed_direction,
                    learn=preview.command.learn,
                    save_with_warning=False,
                    history_entry_id=None,
                ),
            )
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
        if callback.from_user is None or callback.message is None:
            return
        preview = pending_previews.get(callback.from_user.id)
        if preview is None:
            await callback.answer("No pending phrase to save.")
            return
        await callback.answer()
        await _handle_translation_request(
            container=container,
            message=callback.message,
            pending_previews=pending_previews,
            command=TranslatePhraseCommand(
                user_id=preview.command.user_id,
                text=preview.command.text,
                direction=preview.command.direction,
                learn=preview.command.learn,
                save_with_warning=True,
                history_entry_id=preview.command.history_entry_id,
            ),
        )

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
        await _handle_translation_request(
            container=container,
            message=message,
            pending_previews=pending_previews,
        )

    return router
