"""Translation adapter tests."""

from __future__ import annotations

from dataclasses import dataclass

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


@dataclass(slots=True)
class FakeResponse:
    """Minimal HTTP response stub for provider tests."""

    payload: object
    ok: bool = True
    status_code: int = 200
    text: str = ""
    raise_json_error: bool = False

    def json(self) -> object:
        if self.raise_json_error:
            raise ValueError("bad json")
        return self.payload


@dataclass(slots=True)
class FakeSession:
    """Minimal requests session stub."""

    response: FakeResponse | None = None
    error: Exception | None = None
    last_request: dict[str, object] | None = None

    def post(
        self,
        url: str,
        *,
        json: dict[str, object],
        headers: dict[str, str],
        timeout: float,
    ) -> FakeResponse:
        self.last_request = {
            "url": url,
            "json": json,
            "headers": headers,
            "timeout": timeout,
        }
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def test_mock_provider_uses_glossary_and_default_fallback() -> None:
    provider = MockTranslationProvider(
        glossary={("hello", "en", "es"): "hola"}
    )

    glossary_result = provider.translate("hello", "en", "es")
    fallback_result = provider.translate("friend", "en", "it")

    assert glossary_result.translated_text == "hola"
    assert glossary_result.provider_name == "mock"
    assert glossary_result.detected_source_lang == "en"
    assert fallback_result.translated_text == "friend (it)"


def test_yandex_translation_provider_returns_translated_payload() -> None:
    session = FakeSession(
        response=FakeResponse(
            payload={
                "translations": [
                    {
                        "text": "hola",
                        "detectedLanguageCode": "en",
                    }
                ]
            }
        )
    )
    provider = YandexTranslationProvider(
        api_key="token",
        folder_id="folder",
        endpoint_url="https://example.test/translate",
        session=session,
    )

    result = provider.translate("hello", "en", "es")

    assert result.translated_text == "hola"
    assert result.provider_name == "yandex"
    assert result.detected_source_lang == "en"
    assert session.last_request is not None
    assert session.last_request["json"]["texts"] == ["hello"]


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (requests.Timeout("timeout"), "Translation service timed out."),
        (
            requests.RequestException("boom"),
            "Translation service request failed.",
        ),
    ],
)
def test_yandex_translation_provider_maps_request_errors(
    error: Exception,
    message: str,
) -> None:
    provider = YandexTranslationProvider(
        api_key="token",
        folder_id="folder",
        endpoint_url="https://example.test/translate",
        session=FakeSession(error=error),
    )

    with pytest.raises(TranslationProviderError, match=message):
        provider.translate("hello", "en", "es")


def test_yandex_translation_provider_validates_payload_shapes() -> None:
    response = FakeResponse(payload=None, raise_json_error=True)
    with pytest.raises(
        TranslationProviderError,
        match="returned invalid JSON",
    ):
        YandexTranslationProvider._parse_response_payload(response)

    with pytest.raises(
        TranslationProviderError,
        match="unexpected payload",
    ):
        YandexTranslationProvider._parse_response_payload(
            FakeResponse(payload=["bad"])
        )

    with pytest.raises(
        TranslationProviderError,
        match="returned no translations",
    ):
        YandexTranslationProvider._extract_translation_payload({})

    with pytest.raises(
        TranslationProviderError,
        match="invalid translation item",
    ):
        YandexTranslationProvider._extract_translation_payload(
            {"translations": ["bad"]}
        )

    with pytest.raises(
        TranslationProviderError,
        match="empty translation",
    ):
        YandexTranslationProvider._extract_translation_payload(
            {"translations": [{"text": "   "}]}
        )

    with pytest.raises(
        TranslationProviderError,
        match="invalid source language",
    ):
        YandexTranslationProvider._extract_translation_payload(
            {
                "translations": [
                    {
                        "text": "hola",
                        "detectedLanguageCode": 42,
                    }
                ]
            }
        )


def test_yandex_translation_provider_maps_http_error_responses() -> None:
    invalid_language = FakeResponse(
        payload={},
        ok=False,
        status_code=400,
        text="unsupported language code",
    )
    generic_failure = FakeResponse(
        payload={},
        ok=False,
        status_code=500,
        text="internal error",
    )

    with pytest.raises(InvalidSettingsError, match="not supported"):
        YandexTranslationProvider._raise_for_error_response(
            invalid_language
        )

    with pytest.raises(
        TranslationProviderError,
        match="request failed",
    ):
        YandexTranslationProvider._raise_for_error_response(
            generic_failure
        )

    assert YandexTranslationProvider._is_invalid_language_response(
        invalid_language
    )
    assert not YandexTranslationProvider._is_invalid_language_response(
        generic_failure
    )
