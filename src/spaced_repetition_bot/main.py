"""FastAPI application entrypoint."""

import logging

from fastapi import FastAPI

from spaced_repetition_bot.bootstrap import build_container
from spaced_repetition_bot.presentation.api import build_api_router


def create_app() -> FastAPI:
    """Create the FastAPI app."""

    container = build_container()
    if not container.config.debug:
        logging.getLogger("uvicorn.access").disabled = True
    app = FastAPI(
        title=container.config.app_name,
        version=container.config.app_version,
        description=(
            "MVP service for a Telegram-based translator "
            "with spaced repetition scheduling."
        ),
    )
    app.include_router(
        build_api_router(container), prefix=container.config.api_prefix
    )
    return app


app = create_app()
