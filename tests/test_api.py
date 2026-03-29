"""API contract and behavior tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from spaced_repetition_bot.application.errors import ApplicationError
    from spaced_repetition_bot.bootstrap import ApplicationContainer
    from spaced_repetition_bot.infrastructure.config import AppConfig
    from spaced_repetition_bot.presentation.api import (
        build_api_router,
        to_http_exception,
    )
    from tests.support import (
        NoOpReminderService,
        build_test_dependencies,
        build_test_use_cases,
    )
except (
    ImportError
):  # pragma: no cover - exercised in CI with full deps installed.
    pytest.skip(
        "FastAPI test dependencies are not installed.", allow_module_level=True
    )


@dataclass(slots=True)
class ApiTestContext:
    """Stateful API test context."""

    app: FastAPI
    client: TestClient
    container: ApplicationContainer
    clock: object


def build_api_test_context() -> ApiTestContext:
    """Build a deterministic API application for tests."""

    now = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
    dependencies = build_test_dependencies(now)
    use_cases = build_test_use_cases(dependencies)
    container = ApplicationContainer(
        config=AppConfig(
            app_name="Test API", app_version="9.9.9", api_prefix="/api/test"
        ),
        translate_phrase=use_cases["translate"],
        get_history=use_cases["get_history"],
        toggle_learning=use_cases["toggle"],
        get_due_reviews=use_cases["due"],
        start_quiz_session=use_cases["start_quiz"],
        skip_quiz_session=use_cases["skip_quiz"],
        submit_active_quiz_answer=use_cases["submit_active_quiz"],
        submit_review_answer=use_cases["answer"],
        get_user_progress=use_cases["progress"],
        get_settings=use_cases["get_settings"],
        update_settings=use_cases["update_settings"],
        settings_repository=dependencies["settings_repository"],
        clock=dependencies["clock"],
        reminder_service=NoOpReminderService(),
    )
    app = FastAPI(
        title=container.config.app_name,
        version=container.config.app_version,
        description="Test application",
    )
    app.include_router(
        build_api_router(container), prefix=container.config.api_prefix
    )
    return ApiTestContext(
        app=app,
        client=TestClient(app),
        container=container,
        clock=dependencies["clock"],
    )


@pytest.fixture
def api_context() -> ApiTestContext:
    """Provide a fresh API test context."""

    return build_api_test_context()


def response_has_example(response: dict[str, object]) -> bool:
    """Return whether an OpenAPI response object defines an example."""

    for media in response.get("content", {}).values():
        if "example" in media:
            return True
        if media.get("examples"):
            return True
    return False


def request_body_has_description(request_body: dict[str, object]) -> bool:
    """Return whether an OpenAPI request body is described."""

    if request_body.get("description"):
        return True

    for media in request_body.get("content", {}).values():
        schema = media.get("schema", {})
        if schema.get("description"):
            return True
    return False


def iter_operations(
    schema: dict[str, object],
) -> list[tuple[str, str, dict[str, object]]]:
    """Flatten path operations from an OpenAPI schema."""

    operations: list[tuple[str, str, dict[str, object]]] = []
    for path, methods in schema["paths"].items():
        for method, operation in methods.items():
            operations.append((path, method, operation))
    return operations


def test_health_endpoint_returns_service_metadata(
    api_context: ApiTestContext,
) -> None:
    response = api_context.client.get("/api/test/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "9.9.9"}


def test_api_flow_covers_translation_history_progress_settings_and_reviews(
    api_context: ApiTestContext,
) -> None:
    translation_response = api_context.client.post(
        "/api/test/translations",
        json={
            "user_id": 1,
            "text": "good luck",
            "direction": "forward",
            "learn": True,
        },
    )
    assert translation_response.status_code == 201
    card_id = translation_response.json()["card_id"]
    assert translation_response.json()["direction"] == "forward"
    assert translation_response.json()["source_lang"] == "en"
    assert translation_response.json()["target_lang"] == "es"

    history_response = api_context.client.get(
        "/api/test/history", params={"user_id": 1}
    )
    assert history_response.status_code == 200
    assert history_response.json()[0]["source_text"] == "good luck"

    progress_response = api_context.client.get(
        "/api/test/progress", params={"user_id": 1}
    )
    assert progress_response.status_code == 200
    assert progress_response.json()["total_cards"] == 1

    settings_response = api_context.client.get(
        "/api/test/settings", params={"user_id": 1}
    )
    assert settings_response.status_code == 200
    assert settings_response.json()["timezone"] == "UTC"

    update_response = api_context.client.put(
        "/api/test/settings",
        json={
            "user_id": 1,
            "default_source_lang": "de",
            "default_target_lang": "it",
            "default_translation_direction": "reverse",
            "timezone": "Europe/Berlin",
            "notification_time_local": "08:15:00",
            "notifications_enabled": False,
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["default_source_lang"] == "de"
    assert update_response.json()["default_translation_direction"] == "reverse"

    api_context.clock.current += timedelta(days=2)

    due_response = api_context.client.get(
        "/api/test/reviews/due", params={"user_id": 1}
    )
    assert due_response.status_code == 200
    assert len(due_response.json()) == 2

    answer_response = api_context.client.post(
        f"/api/test/reviews/{card_id}/answer",
        json={
            "user_id": 1,
            "direction": "forward",
            "answer_text": "buena suerte",
        },
    )
    assert answer_response.status_code == 200
    assert answer_response.json()["outcome"] == "correct"

    toggle_response = api_context.client.patch(
        f"/api/test/cards/{card_id}/learning",
        json={"user_id": 1, "learning_enabled": False},
    )
    assert toggle_response.status_code == 200
    assert toggle_response.json()["learning_status"] == "not_learning"


def test_api_maps_not_found_not_due_and_learning_disabled_errors(
    api_context: ApiTestContext,
) -> None:
    not_found_response = api_context.client.post(
        f"/api/test/reviews/{uuid4()}/answer",
        json={
            "user_id": 1,
            "direction": "forward",
            "answer_text": "buena suerte",
        },
    )
    assert not_found_response.status_code == 404

    create_response = api_context.client.post(
        "/api/test/translations",
        json={
            "user_id": 1,
            "text": "good luck",
            "direction": "forward",
            "learn": True,
        },
    )
    card_id = create_response.json()["card_id"]

    not_due_response = api_context.client.post(
        f"/api/test/reviews/{card_id}/answer",
        json={
            "user_id": 1,
            "direction": "forward",
            "answer_text": "buena suerte",
        },
    )
    assert not_due_response.status_code == 400

    api_context.client.patch(
        f"/api/test/cards/{card_id}/learning",
        json={"user_id": 1, "learning_enabled": False},
    )
    api_context.clock.current += timedelta(days=2)
    disabled_response = api_context.client.post(
        f"/api/test/reviews/{card_id}/answer",
        json={
            "user_id": 1,
            "direction": "forward",
            "answer_text": "buena suerte",
        },
    )
    assert disabled_response.status_code == 409

    missing_card_response = api_context.client.patch(
        f"/api/test/cards/{uuid4()}/learning",
        json={"user_id": 1, "learning_enabled": False},
    )
    assert missing_card_response.status_code == 404


def test_openapi_contract_contains_descriptions_and_response_examples(
    api_context: ApiTestContext,
) -> None:
    schema = api_context.app.openapi()

    for path, method, operation in iter_operations(schema):
        assert operation[
            "description"
        ], f"{method.upper()} {path} is missing a description"
        for parameter in operation.get("parameters", []):
            assert parameter["description"], (
                f"{method.upper()} {path} parameter "
                f"{parameter['name']} lacks a description"
            )
        if "requestBody" in operation:
            assert request_body_has_description(
                operation["requestBody"]
            ), f"{method.upper()} {path} request body lacks a description"
        documented_responses = {
            code: response
            for code, response in operation["responses"].items()
            if code != "422"
        }
        assert any(
            response_has_example(response)
            for response in documented_responses.values()
        ), f"{method.upper()} {path} has no documented response examples"


def test_to_http_exception_returns_500_for_unknown_error() -> None:
    class UnknownApplicationError(ApplicationError):
        """Synthetic error used for fallback testing."""

    error = to_http_exception(UnknownApplicationError("boom"))

    assert error.status_code == 500
    assert error.detail == "Unexpected application error."
