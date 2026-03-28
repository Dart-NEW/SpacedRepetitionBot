"""Translation endpoint registration."""

from __future__ import annotations

from fastapi import APIRouter, Body, status

from spaced_repetition_bot.application.dtos import TranslatePhraseCommand
from spaced_repetition_bot.bootstrap import ApplicationContainer
from spaced_repetition_bot.presentation.api_translation_models import (
    ScheduledReviewResponse,
    TranslationRequest,
    TranslationResponse,
)


def add_translation_routes(
    router: APIRouter, container: ApplicationContainer
) -> None:
    """Register translation routes."""

    @router.post(
        "/translations",
        response_model=TranslationResponse,
        status_code=status.HTTP_201_CREATED,
        summary="Translate a phrase",
        description="Translate text and optionally create a learning card.",
        responses={
            201: {
                "description": "Phrase translated and stored.",
                "content": {
                    "application/json": {
                        "example": {
                            "card_id": "11111111-1111-1111-1111-111111111111",
                            "source_text": "good luck",
                            "translated_text": "good luck (es)",
                            "source_lang": "en",
                            "target_lang": "es",
                            "learning_status": "active",
                            "provider_name": "mock",
                            "scheduled_reviews": [
                                {
                                    "direction": "forward",
                                    "step_index": 0,
                                    "next_review_at": "2026-03-30T12:00:00Z",
                                    "completed": False,
                                },
                                {
                                    "direction": "reverse",
                                    "step_index": 0,
                                    "next_review_at": "2026-03-30T12:00:00Z",
                                    "completed": False,
                                },
                            ],
                        }
                    }
                },
            }
        },
    )
    def create_translation(
        payload: TranslationRequest = Body(
            description="Translation request payload.",
            examples=[
                {
                    "user_id": 123456789,
                    "text": "good luck",
                    "source_lang": "en",
                    "target_lang": "es",
                    "learn": True,
                }
            ],
        ),
    ) -> TranslationResponse:
        result = container.translate_phrase.execute(
            TranslatePhraseCommand(
                user_id=payload.user_id,
                text=payload.text,
                source_lang=payload.source_lang,
                target_lang=payload.target_lang,
                learn=payload.learn,
            )
        )
        return TranslationResponse(
            card_id=result.card_id,
            source_text=result.source_text,
            translated_text=result.translated_text,
            source_lang=result.source_lang,
            target_lang=result.target_lang,
            learning_status=result.learning_status,
            provider_name=result.provider_name,
            scheduled_reviews=[
                ScheduledReviewResponse.model_validate(
                    item, from_attributes=True
                )
                for item in result.scheduled_reviews
            ],
        )
