"""FastAPI contract and error-mapping tests."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest

from spaced_repetition_bot.application.errors import (
    ApplicationError,
    InvalidSettingsError,
    TranslationProviderError,
)
from spaced_repetition_bot.presentation.api import to_http_exception

pytestmark = pytest.mark.contract


def test_health_endpoint_returns_service_metadata(api_client) -> None:
    response = api_client.get("/api/test/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "9.9.9"}


def test_api_flow_covers_settings_translation_history_progress_and_reviews(
    api_client,
    container_clock,
    fixed_now,
) -> None:
    settings_response = api_client.put(
        "/api/test/settings",
        json={
            "user_id": 1,
            "default_source_lang": "en",
            "default_target_lang": "es",
            "default_translation_direction": "forward",
            "timezone": "UTC",
            "notification_time_local": "09:00:00",
            "notifications_enabled": True,
        },
    )
    translation_response = api_client.post(
        "/api/test/translations",
        json={
            "user_id": 1,
            "text": "good luck",
            "direction": "forward",
            "learn": True,
        },
    )
    card_id = translation_response.json()["card_id"]
    history_response = api_client.get(
        "/api/test/history",
        params={"user_id": 1, "limit": 20},
    )
    progress_response = api_client.get(
        "/api/test/progress",
        params={"user_id": 1},
    )
    settings_get_response = api_client.get(
        "/api/test/settings",
        params={"user_id": 1},
    )
    container_clock.current = fixed_now + timedelta(days=2)
    due_response = api_client.get(
        "/api/test/reviews/due",
        params={"user_id": 1},
    )
    answer_response = api_client.post(
        f"/api/test/reviews/{card_id}/answer",
        json={
            "user_id": 1,
            "direction": "forward",
            "answer_text": "buena suerte",
        },
    )
    toggle_response = api_client.patch(
        f"/api/test/cards/{card_id}/learning",
        json={"user_id": 1, "learning_enabled": False},
    )

    assert settings_response.status_code == 200
    assert translation_response.status_code == 201
    assert history_response.json()[0]["source_text"] == "good luck"
    assert progress_response.json()["total_cards"] == 1
    assert (
        settings_get_response.json()["default_translation_direction"]
        == "forward"
    )
    assert len(due_response.json()) == 2
    assert answer_response.json()["outcome"] == "correct"
    assert toggle_response.json()["learning_status"] == "not_learning"


def test_api_maps_application_errors_to_http_responses(
    api_client,
    test_container,
    container_clock,
    fixed_now,
    monkeypatch,
) -> None:
    missing_card = api_client.post(
        f"/api/test/reviews/{uuid4()}/answer",
        json={
            "user_id": 1,
            "direction": "forward",
            "answer_text": "buena suerte",
        },
    )
    translation_response = api_client.post(
        "/api/test/translations",
        json={
            "user_id": 1,
            "text": "good luck",
            "learn": True,
        },
    )
    card_id = translation_response.json()["card_id"]
    not_due = api_client.post(
        f"/api/test/reviews/{card_id}/answer",
        json={
            "user_id": 1,
            "direction": "forward",
            "answer_text": "buena suerte",
        },
    )
    container_clock.current = fixed_now + timedelta(days=2)
    api_client.patch(
        f"/api/test/cards/{card_id}/learning",
        json={"user_id": 1, "learning_enabled": False},
    )
    disabled = api_client.post(
        f"/api/test/reviews/{card_id}/answer",
        json={
            "user_id": 1,
            "direction": "forward",
            "answer_text": "buena suerte",
        },
    )

    def raise_provider_error(_self, _command):
        raise TranslationProviderError("boom")

    monkeypatch.setattr(
        type(test_container.translate_phrase),
        "execute",
        raise_provider_error,
    )
    provider_failure = api_client.post(
        "/api/test/translations",
        json={
            "user_id": 1,
            "text": "good luck",
            "learn": True,
        },
    )

    assert missing_card.status_code == 404
    assert not_due.status_code == 400
    assert disabled.status_code == 409
    assert provider_failure.status_code == 502


def test_api_returns_500_for_unexpected_application_error(
    api_client,
    test_container,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        type(test_container.get_history),
        "execute",
        lambda _self, _query: (_ for _ in ()).throw(ApplicationError("boom")),
    )

    response = api_client.get("/api/test/history", params={"user_id": 1})

    assert response.status_code == 500
    assert response.json()["detail"] == "Unexpected application error."


def test_api_validates_payloads_and_query_constraints(api_client) -> None:
    invalid_settings = api_client.put(
        "/api/test/settings",
        json={
            "user_id": 1,
            "default_source_lang": "en",
            "default_target_lang": "en",
            "default_translation_direction": "forward",
            "timezone": "UTC",
            "notification_time_local": "09:00:00",
            "notifications_enabled": True,
        },
    )
    invalid_query = api_client.get(
        "/api/test/history",
        params={"user_id": 1, "limit": 101},
    )
    invalid_body = api_client.post(
        "/api/test/translations",
        json={"user_id": 1},
    )

    assert invalid_settings.status_code == 400
    assert invalid_query.status_code == 422
    assert invalid_body.status_code == 422


def test_openapi_contract_contains_descriptions_examples_and_prefixed_routes(
    api_app,
) -> None:
    schema = api_app.openapi()
    paths = schema["paths"]

    assert "/api/test/health" in paths
    assert paths["/api/test/translations"]["post"]["description"]
    assert (
        paths["/api/test/translations"]["post"]["responses"]["201"][
            "content"
        ]["application/json"]["example"]["scheduled_reviews"]
    )


def test_http_exception_mapping_preserves_invalid_settings_message() -> None:
    error = InvalidSettingsError("bad settings")
    mapped = to_http_exception(error)

    assert mapped.status_code == 400
    assert mapped.detail == "bad settings"
