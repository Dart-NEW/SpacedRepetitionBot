"""Telegram bot polling entrypoint."""

from __future__ import annotations

import asyncio
from contextlib import suppress

from aiogram import Bot, Dispatcher

from spaced_repetition_bot.bootstrap import build_container
from spaced_repetition_bot.presentation.telegram import build_telegram_router


async def run() -> None:
    """Start the Telegram bot with long polling."""

    container = build_container()
    bot = Bot(token=container.config.telegram_bot_token)
    dispatcher = Dispatcher()
    dispatcher.include_router(build_telegram_router(container))
    reminder_task = asyncio.create_task(container.reminder_service.run(bot))
    try:
        await dispatcher.start_polling(bot)
    finally:
        reminder_task.cancel()
        with suppress(asyncio.CancelledError):
            await reminder_task


def main() -> None:
    """Synchronous launcher for CLI execution."""

    asyncio.run(run())


if __name__ == "__main__":
    main()
