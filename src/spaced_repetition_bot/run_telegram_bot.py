"""Telegram bot polling entrypoint."""

# Runtime sequence:
# - Build the application container once at process startup.
# - Create the aiogram bot using the configured Telegram token.
# - Register command shortcuts and the chat menu before polling starts.
# - Mount the Telegram router produced by the presentation layer.
# - Start the reminder loop as a background task owned by this process.
# - Run long polling until Telegram stops the session or the process exits.
# - On shutdown, cancel the reminder task before returning control.
# - Cancellation is suppressed only for the expected `CancelledError` case.
# - The synchronous `main` wrapper keeps CLI execution straightforward.
# - Tests patch this module to verify polling and reminder task lifecycle.
# - No business rules live here; the file is orchestration only.
# - That boundary keeps startup failures narrow and easy to reason about.
# - Bot UI registration stays separate from command handler construction.
# - The container remains the single place where dependencies are wired.
# - This module should stay small and process-oriented.
# - If deployment changes from polling to webhooks, this is the entrypoint.
# - The reminder task is intentionally colocated with polling for the MVP.
# - Future process separation can happen without changing use cases.
# - Keeping the control flow explicit helps operational troubleshooting.
# - It also improves maintainability for the runtime bootstrap path.

from __future__ import annotations

import asyncio
from contextlib import suppress

from aiogram import Bot, Dispatcher

from spaced_repetition_bot.bootstrap import build_container
from spaced_repetition_bot.presentation.telegram import (
    build_telegram_router,
    configure_telegram_bot_ui,
)


async def run() -> None:
    """Start the Telegram bot with long polling."""

    container = build_container()
    bot = Bot(token=container.config.telegram_bot_token)
    await configure_telegram_bot_ui(bot)
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
