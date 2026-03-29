"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager
import logging

import anyio.to_thread
from fastapi import FastAPI

from spaced_repetition_bot.bootstrap import build_container
from spaced_repetition_bot.presentation.api import build_api_router

API_THREADPOOL_TOKENS = 200


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    limiter = anyio.to_thread.current_default_thread_limiter()
    limiter.total_tokens = max(limiter.total_tokens, API_THREADPOOL_TOKENS)
    yield


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
        lifespan=_lifespan,
    )
    app.include_router(
        build_api_router(container), prefix=container.config.api_prefix
    )
    return app


app = create_app()
