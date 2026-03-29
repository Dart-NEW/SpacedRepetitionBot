"""Shared pytest fixtures."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from spaced_repetition_bot.presentation.api import build_api_router
from tests.support.builders import (
    FixedClock,
    build_api_test_app,
    build_test_container,
    build_test_dependencies,
    build_test_use_cases,
)


@pytest.fixture
def fixed_now() -> datetime:
    """Return a deterministic baseline timestamp."""

    return datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def test_dependencies(fixed_now: datetime) -> dict[str, object]:
    """Provide shared in-memory dependencies for unit tests."""

    return build_test_dependencies(fixed_now)


@pytest.fixture
def test_use_cases(
    test_dependencies: dict[str, object],
) -> dict[str, object]:
    """Provide a canonical set of runtime use cases."""

    return build_test_use_cases(test_dependencies)


@pytest.fixture
def fixed_clock(test_dependencies: dict[str, object]) -> FixedClock:
    """Expose the deterministic clock."""

    return test_dependencies["clock"]


@pytest.fixture
def test_container(fixed_now: datetime):
    """Provide a fully wired application container."""

    return build_test_container(fixed_now)


@pytest.fixture
def container_clock(test_container) -> FixedClock:
    """Expose the deterministic clock used by the full container."""

    return test_container.clock


@pytest.fixture
def api_app(test_container) -> FastAPI:
    """Provide a FastAPI test application."""

    return build_api_test_app(test_container)


@pytest.fixture
def api_client(api_app: FastAPI) -> TestClient:
    """Provide a synchronous API client."""

    return TestClient(api_app, raise_server_exceptions=False)
