"""aiogram presentation layer."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from spaced_repetition_bot.application.dtos import (
    GetHistoryQuery,
    GetUserProgressQuery,
    TranslatePhraseCommand,
)
from spaced_repetition_bot.bootstrap import ApplicationContainer


def build_telegram_router(container: ApplicationContainer) -> Router:
    """Build a minimal Telegram router for the MVP."""

    router = Router(name="spaced-repetition-bot")

    @router.message(CommandStart())
    async def handle_start(message: Message) -> None:
        if message.from_user is None:
            return
        await message.answer(
            "Send me a phrase and I will translate it "
            "and add it to your review queue."
        )

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
            f"{item.source_text} -> {item.translated_text}"
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

    @router.message(F.text)
    async def handle_translation(message: Message) -> None:
        if message.from_user is None or message.text is None:
            return
        result = container.translate_phrase.execute(
            TranslatePhraseCommand(
                user_id=message.from_user.id,
                text=message.text,
            )
        )
        await message.answer(
            f"{result.source_text} -> {result.translated_text}\n"
            f"Learning status: {result.learning_status}"
        )

    return router
