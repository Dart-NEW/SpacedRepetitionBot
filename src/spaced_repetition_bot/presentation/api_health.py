"""Health endpoint registration."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from spaced_repetition_bot.bootstrap import ApplicationContainer


class HealthResponse(BaseModel):
    """Service health response."""

    status: str = Field(description="Current service state.", examples=["ok"])
    version: str = Field(
        description="Application version.", examples=["0.1.0"]
    )


def add_health_routes(
    router: APIRouter, container: ApplicationContainer
) -> None:
    """Register health routes."""

    @router.get(
        "/health",
        response_model=HealthResponse,
        summary="Health check",
        description="Return basic health information for the service.",
        responses={
            200: {
                "description": "Service is healthy.",
                "content": {
                    "application/json": {
                        "example": {"status": "ok", "version": "0.1.0"}
                    }
                },
            }
        },
    )
    def health_check() -> HealthResponse:
        return HealthResponse(
            status="ok", version=container.config.app_version
        )
