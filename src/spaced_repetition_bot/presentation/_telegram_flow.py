"""Telegram flow helpers used by the router."""

# Flow helper map:
# - This module contains the async steps behind Telegram handlers.
# - It coordinates use cases, formatting helpers, and reply markup.
# - Router callbacks stay thin by delegating here.
# - History, progress, and settings rendering are grouped together.
# - Quiz start, skip, answer, and summary behavior lives here too.
# - Guided settings input is handled as a small state machine.
# - Translation preview handling also stays in this module.
# - These helpers are stateful in behavior, but not in storage ownership.
# - Persistent state still belongs to repositories behind use cases.
# - Message ids are stored here because that is a Telegram concern.
# - Error mapping is intentionally user-facing and chat-oriented.
# - The flow keeps invalid commands from leaking stack traces to users.
# - Pure string and keyboard logic is imported from `_telegram_ui`.
# - That separation keeps this module focused on orchestration.
# - Tests exercise most functions here through router callbacks.
# - A few helpers remain directly callable for narrower contract tests.
# - If the quiz UX changes, this is the first file to inspect.
# - If the visual wording changes, `_telegram_ui` is the right place.
# - The split improves readability without changing external behavior.
# - The public `presentation.telegram` facade remains backward compatible.

from __future__ import annotations

import asyncio
from datetime import time
from uuid import UUID

from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from spaced_repetition_bot.application.dtos import (
    ActiveQuizAnswerResult,
    GetHistoryQuery,
    GetSettingsQuery,
    GetUserProgressQuery,
    QuizSessionSummary,
    SkipQuizResult,
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
from spaced_repetition_bot.presentation._telegram_ui import (
    HISTORY_PAGE_SIZE,
    SHORT_ID_LOOKUP_LIMIT,
    PendingInputState,
    PendingTranslationPreview,
    _build_home_keyboard,
    _build_quiz_intro_keyboard,
    _build_quiz_reply_keyboard,
    _build_settings_keyboard,
    _build_summary_keyboard,
    _build_translation_keyboard,
    _format_history_card,
    _format_learning_status,
    _format_progress_card,
    _format_quiz_feedback,
    _format_quiz_intro,
    _format_quiz_prompt,
    _format_settings_card,
    _format_short_card_id,
    _format_summary,
    _format_translation_card,
    _is_valid_timezone,
    _parse_notification_frequency_days,
    _parse_notification_time,
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
    if state.kind == "notifyevery":
        return await _handle_notify_every_input(container, message)
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


async def _handle_notify_every_input(
    container: ApplicationContainer,
    message: Message,
) -> bool:
    notification_frequency_days = _parse_notification_frequency_days(
        message.text
    )
    if notification_frequency_days is None:
        await message.answer(
            "Send the reminder frequency as a whole number of days.\n"
            "Use /cancel to stop."
        )
        return False
    await _update_settings(
        container=container,
        message=message,
        notification_frequency_days=notification_frequency_days,
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
    notification_frequency_days: int | None = None,
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
                notification_frequency_days=(
                    current.notification_frequency_days
                    if notification_frequency_days is None
                    else notification_frequency_days
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
    command,
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
    matches = {
        item.card_id
        for item in history
        if item.card_id is not None
        and _format_short_card_id(item.card_id).casefold() == short_id
    }
    if len(matches) != 1:
        return None
    return next(iter(matches))


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
    pending_previews: dict[int, PendingTranslationPreview],
    command: TranslatePhraseCommand | None = None,
) -> None:
    if message.from_user is None or message.text is None:
        return
    active_command = command or TranslatePhraseCommand(
        user_id=message.from_user.id,
        text=message.text,
        save_with_warning=False,
    )
    try:
        result = await asyncio.to_thread(
            container.translate_phrase.execute,
            active_command,
        )
    except TranslationProviderError:
        await message.answer("Translation provider is unavailable right now.")
        return
    except ApplicationError as error:
        await message.answer(str(error))
        return
    if result.saved:
        pending_previews.pop(message.from_user.id, None)
    elif result.has_pair_warning:
        pending_previews[message.from_user.id] = PendingTranslationPreview(
            command=TranslatePhraseCommand(
                user_id=active_command.user_id,
                text=active_command.text,
                direction=result.direction,
                learn=active_command.learn,
                save_with_warning=False,
                history_entry_id=result.history_entry_id,
            )
        )
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
            show_warning_actions=result.has_pair_warning and not result.saved,
        ),
    )
