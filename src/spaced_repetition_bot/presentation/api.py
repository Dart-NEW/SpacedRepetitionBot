"""FastAPI presentation layer."""

from __future__ import annotations

from fastapi import APIRouter

from spaced_repetition_bot.bootstrap import ApplicationContainer
from spaced_repetition_bot.presentation.api_due_reviews import (
    add_due_review_routes,
)
from spaced_repetition_bot.presentation.api_errors import to_http_exception
from spaced_repetition_bot.presentation.api_health import add_health_routes
from spaced_repetition_bot.presentation.api_history import add_history_routes
from spaced_repetition_bot.presentation.api_learning import (
    add_learning_routes,
)
from spaced_repetition_bot.presentation.api_progress import (
    add_progress_routes,
)
from spaced_repetition_bot.presentation.api_settings import (
    add_settings_routes,
)
from spaced_repetition_bot.presentation.api_submit_review import (
    add_submit_review_routes,
)
from spaced_repetition_bot.presentation.api_translations import (
    add_translation_routes,
)


def build_api_router(container: ApplicationContainer) -> APIRouter:
    """Create an API router bound to the application container."""

    router = APIRouter(tags=["spaced-repetition-bot"])
    add_health_routes(router, container)
    add_translation_routes(router, container)
    add_history_routes(router, container)
    add_learning_routes(router, container)
    add_due_review_routes(router, container)
    add_submit_review_routes(router, container)
    add_progress_routes(router, container)
    add_settings_routes(router, container)
    return router


__all__ = ["build_api_router", "to_http_exception"]
