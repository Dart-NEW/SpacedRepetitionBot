"""Presentation adapters."""

from spaced_repetition_bot.presentation.api import build_api_router
from spaced_repetition_bot.presentation.telegram import build_telegram_router

__all__ = ["build_api_router", "build_telegram_router"]
