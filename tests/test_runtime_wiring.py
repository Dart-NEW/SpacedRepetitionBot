"""Runtime wiring tests for configuration and app assembly."""

from __future__ import annotations

from datetime import timezone

import pytest

try:
    from spaced_repetition_bot.application.dtos import (
        GetHistoryQuery,
        TranslatePhraseCommand,
    )
    from spaced_repetition_bot.bootstrap import build_container
    from spaced_repetition_bot.infrastructure.clock import SystemClock
    from spaced_repetition_bot.infrastructure.config import AppConfig
    from spaced_repetition_bot.domain.enums import ReviewDirection
    from spaced_repetition_bot.main import create_app
    from spaced_repetition_bot.presentation import (
        build_api_router,
        build_telegram_router,
    )
except (
    ImportError
):  # pragma: no cover - exercised in CI with full deps installed.
    pytest.skip(
        "Runtime dependencies are not installed.", allow_module_level=True
    )


def test_app_config_reads_environment_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SRB_APP_NAME", "Quality Gate Bot")
    monkeypatch.setenv("SRB_APP_VERSION", "1.2.3")
    monkeypatch.setenv("SRB_API_PREFIX", "/api/quality")

    config = AppConfig()

    assert config.app_name == "Quality Gate Bot"
    assert config.app_version == "1.2.3"
    assert config.api_prefix == "/api/quality"


def test_system_clock_returns_timezone_aware_utc_datetime() -> None:
    current_time = SystemClock().now()

    assert current_time.tzinfo == timezone.utc


def test_build_container_wires_use_cases_against_shared_repositories() -> None:
    container = build_container(
        AppConfig(
            app_name="Test App", app_version="2.0.0", api_prefix="/api/test"
        )
    )

    translation = container.translate_phrase.execute(
        TranslatePhraseCommand(
            user_id=1,
            text="hello",
        )
    )
    history = container.get_history.execute(GetHistoryQuery(user_id=1))

    assert history[0].card_id == translation.card_id
    assert translation.direction is ReviewDirection.FORWARD
    assert translation.source_lang == "en"
    assert translation.target_lang == "es"
    assert container.config.app_name == "Test App"


def test_create_app_registers_prefixed_routes_and_metadata() -> None:
    app = create_app()
    route_paths = {route.path for route in app.routes}

    assert app.title == "Spaced Repetition Bot"
    assert app.version == "0.1.0"
    assert "/api/v1/health" in route_paths


def test_presentation_package_exports_router_builders() -> None:
    assert callable(build_api_router)
    assert callable(build_telegram_router)
