"""Translation adapters."""

from __future__ import annotations

from dataclasses import dataclass, field

import requests
from requests.adapters import HTTPAdapter
from requests import Response, Session

from spaced_repetition_bot.application.errors import (
    InvalidSettingsError,
    TranslationProviderError,
)
from spaced_repetition_bot.application.dtos import TranslationGatewayResult

YANDEX_HTTP_POOL_SIZE = 100


@dataclass(slots=True)
class MockTranslationProvider:
    """Deterministic provider for local development and tests."""

    glossary: dict[tuple[str, str, str], str] = field(default_factory=dict)

    def translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
    ) -> TranslationGatewayResult:
        """Return a deterministic translation-like string."""

        key = (
            text.strip().casefold(),
            source_lang.casefold(),
            target_lang.casefold(),
        )
        translated_text = self.glossary.get(
            key, f"{text.strip()} ({target_lang.lower()})"
        )
        return TranslationGatewayResult(
            translated_text=translated_text,
            provider_name="mock",
            detected_source_lang=source_lang,
        )


@dataclass(slots=True)
class YandexTranslationProvider:
    """Yandex Cloud Translate adapter."""

    api_key: str
    folder_id: str
    endpoint_url: str
    timeout_seconds: float = 10.0
    session: Session = field(default_factory=Session)

    def __post_init__(self) -> None:
        adapter = HTTPAdapter(
            pool_connections=YANDEX_HTTP_POOL_SIZE,
            pool_maxsize=YANDEX_HTTP_POOL_SIZE,
        )
        if not hasattr(self.session, "mount"):
            return
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
    ) -> TranslationGatewayResult:
        """Translate text with Yandex Cloud Translate."""

        response = self._post_translation_request(
            text=text,
            source_lang=source_lang,
            target_lang=target_lang,
        )
        payload = self._parse_response_payload(response)
        translated_text, detected_source_lang = (
            self._extract_translation_payload(payload)
        )
        return TranslationGatewayResult(
            translated_text=translated_text,
            provider_name="yandex",
            detected_source_lang=detected_source_lang or source_lang,
        )

    def _post_translation_request(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
    ) -> Response:
        body = {
            "folderId": self.folder_id,
            "texts": [text],
            "sourceLanguageCode": source_lang,
            "targetLanguageCode": target_lang,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Api-Key {self.api_key}",
        }
        try:
            response = self.session.post(
                self.endpoint_url,
                json=body,
                headers=headers,
                timeout=self.timeout_seconds,
            )
        except requests.Timeout as error:
            raise TranslationProviderError(
                "Translation service timed out."
            ) from error
        except requests.RequestException as error:
            raise TranslationProviderError(
                "Translation service request failed."
            ) from error
        self._raise_for_error_response(response)
        return response

    @staticmethod
    def _parse_response_payload(response: Response) -> dict[str, object]:
        try:
            payload = response.json()
        except ValueError as error:
            raise TranslationProviderError(
                "Translation service returned invalid JSON."
            ) from error
        if not isinstance(payload, dict):
            raise TranslationProviderError(
                "Translation service returned an unexpected payload."
            )
        return payload

    @staticmethod
    def _extract_translation_payload(
        payload: dict[str, object],
    ) -> tuple[str, str | None]:
        translations = payload.get("translations")
        if not isinstance(translations, list) or not translations:
            raise TranslationProviderError(
                "Translation service returned no translations."
            )
        first_item = translations[0]
        if not isinstance(first_item, dict):
            raise TranslationProviderError(
                "Translation service returned an invalid translation item."
            )
        translated_text = first_item.get("text")
        detected_source_lang = first_item.get("detectedLanguageCode")
        if not isinstance(translated_text, str) or not translated_text.strip():
            raise TranslationProviderError(
                "Translation service returned an empty translation."
            )
        if detected_source_lang is not None and not isinstance(
            detected_source_lang, str
        ):
            raise TranslationProviderError(
                "Translation service returned an invalid source language."
            )
        return translated_text, detected_source_lang

    @staticmethod
    def _raise_for_error_response(response: Response) -> None:
        if response.ok:
            return
        if YandexTranslationProvider._is_invalid_language_response(response):
            raise InvalidSettingsError(
                "Language codes are not supported by the translation provider."
            )
        raise TranslationProviderError("Translation service request failed.")

    @staticmethod
    def _is_invalid_language_response(response: Response) -> bool:
        if response.status_code != 400:
            return False
        body = response.text.casefold()
        invalid_language_markers = (
            "sourcelanguagecode",
            "targetlanguagecode",
            "language code",
            "unsupported",
            "not supported",
        )
        return any(marker in body for marker in invalid_language_markers)
