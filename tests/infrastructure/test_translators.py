"""Infrastructure translation provider tests."""

from __future__ import annotations

import json

import pytest
import requests

from spaced_repetition_bot.application.errors import (
    InvalidSettingsError,
    TranslationProviderError,
)
from spaced_repetition_bot.infrastructure.translators import (
    MockTranslationProvider,
    YandexTranslationProvider,
)

pytestmark = pytest.mark.integration


class FakeResponse:
    """Small response double with requests-like attributes."""

    def __init__(
        self,
        *,
        ok: bool = True,
        status_code: int = 200,
        payload: object | None = None,
        text: str = "",
    ) -> None:
        self.ok = ok
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    """Small session double for Yandex adapter tests."""

    def __init__(self, response_or_error) -> None:
        self.response_or_error = response_or_error
        self.calls: list[dict[str, object]] = []

    def post(self, url: str, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if isinstance(self.response_or_error, Exception):
            raise self.response_or_error
        return self.response_or_error


def test_mock_translation_provider_uses_glossary_and_fallback() -> None:
    provider = MockTranslationProvider(glossary={("hello", "en", "es"): "hola"})

    assert provider.translate(" hello ", "EN", "ES").translated_text == "hola"
    assert provider.translate("bye", "en", "fr").translated_text == "bye (fr)"


def test_yandex_translation_provider_success_builds_expected_request() -> None:
    response = FakeResponse(
        payload={
            "translations": [
                {
                    "text": "hola",
                    "detectedLanguageCode": "en",
                }
            ]
        }
    )
    session = FakeSession(response)
    provider = YandexTranslationProvider(
        api_key="key",
        folder_id="folder",
        endpoint_url="https://example.test/translate",
        timeout_seconds=5.0,
        session=session,
    )

    result = provider.translate("hello", "en", "es")

    assert result.translated_text == "hola"
    assert result.provider_name == "yandex"
    assert result.detected_source_lang == "en"
    assert session.calls[0]["json"]["folderId"] == "folder"
    assert session.calls[0]["headers"]["Authorization"] == "Api-Key key"


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (requests.Timeout(), "Translation service timed out."),
        (requests.RequestException(), "Translation service request failed."),
    ],
)
def test_yandex_translation_provider_maps_transport_errors(
    error: Exception,
    message: str,
) -> None:
    provider = YandexTranslationProvider(
        api_key="key",
        folder_id="folder",
        endpoint_url="https://example.test/translate",
        session=FakeSession(error),
    )

    with pytest.raises(TranslationProviderError, match=message):
        provider.translate("hello", "en", "es")


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (ValueError("bad json"), "Translation service returned invalid JSON."),
        (["not", "a", "dict"], "Translation service returned an unexpected payload."),
        ({}, "Translation service returned no translations."),
        ({"translations": ["bad"]}, "Translation service returned an invalid translation item."),
        ({"translations": [{"text": " "}]} , "Translation service returned an empty translation."),
        (
            {"translations": [{"text": "hola", "detectedLanguageCode": 123}]},
            "Translation service returned an invalid source language.",
        ),
    ],
)
def test_yandex_translation_provider_rejects_invalid_payloads(
    payload: object,
    message: str,
) -> None:
    provider = YandexTranslationProvider(
        api_key="key",
        folder_id="folder",
        endpoint_url="https://example.test/translate",
        session=FakeSession(FakeResponse(payload=payload)),
    )

    with pytest.raises(TranslationProviderError, match=message):
        provider.translate("hello", "en", "es")


def test_yandex_translation_provider_maps_invalid_language_response() -> None:
    provider = YandexTranslationProvider(
        api_key="key",
        folder_id="folder",
        endpoint_url="https://example.test/translate",
        session=FakeSession(
            FakeResponse(
                ok=False,
                status_code=400,
                payload={"code": 3},
                text=json.dumps({"message": "unsupported language code"}),
            )
        ),
    )

    with pytest.raises(
        InvalidSettingsError,
        match="Language codes are not supported by the translation provider.",
    ):
        provider.translate("hello", "en", "es")


def test_yandex_translation_provider_maps_generic_error_response() -> None:
    provider = YandexTranslationProvider(
        api_key="key",
        folder_id="folder",
        endpoint_url="https://example.test/translate",
        session=FakeSession(
            FakeResponse(ok=False, status_code=500, payload={"error": "boom"})
        ),
    )

    with pytest.raises(
        TranslationProviderError,
        match="Translation service request failed.",
    ):
        provider.translate("hello", "en", "es")
