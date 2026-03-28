"""Translation adapters."""

from __future__ import annotations

from dataclasses import dataclass, field

from spaced_repetition_bot.application.dtos import TranslationGatewayResult


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
