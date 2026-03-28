"""FastAPI presentation layer."""

from __future__ import annotations

from datetime import datetime, time
from uuid import UUID

from fastapi import APIRouter, Body, HTTPException, Path, Query, status
from pydantic import BaseModel, ConfigDict, Field

from spaced_repetition_bot.application.dtos import (
    GetHistoryQuery,
    GetSettingsQuery,
    GetUserProgressQuery,
    SubmitReviewAnswerCommand,
    ToggleLearningCommand,
    TranslatePhraseCommand,
    UpdateSettingsCommand,
)
from spaced_repetition_bot.application.errors import (
    ApplicationError,
    CardNotFoundError,
    LearningDisabledError,
    ReviewNotAvailableError,
)
from spaced_repetition_bot.bootstrap import ApplicationContainer
from spaced_repetition_bot.domain.enums import LearningStatus, ReviewDirection, ReviewOutcome


class HealthResponse(BaseModel):
    """Service health response."""

    status: str = Field(description="Current service state.", examples=["ok"])
    version: str = Field(description="Application version.", examples=["0.1.0"])


class ScheduledReviewResponse(BaseModel):
    """Scheduled review details."""

    model_config = ConfigDict(from_attributes=True)

    direction: ReviewDirection = Field(description="Quiz direction.", examples=["forward"])
    step_index: int = Field(description="Current review step index.", examples=[0])
    next_review_at: datetime | None = Field(
        description="When the next review is due.",
        examples=["2026-03-30T12:00:00Z"],
    )
    completed: bool = Field(description="Whether the review track is completed.", examples=[False])


class TranslationRequest(BaseModel):
    """Input payload for phrase translation."""

    user_id: int = Field(description="Telegram user id.", examples=[123456789])
    text: str = Field(description="Phrase to translate and optionally learn.", examples=["good luck"])
    source_lang: str | None = Field(
        default=None,
        description="Explicit source language code. Falls back to user settings.",
        examples=["en"],
    )
    target_lang: str | None = Field(
        default=None,
        description="Explicit target language code. Falls back to user settings.",
        examples=["es"],
    )
    learn: bool = Field(
        default=True,
        description="Whether the phrase should be added to the learning queue.",
        examples=[True],
    )


class TranslationResponse(BaseModel):
    """Output payload for a translation command."""

    card_id: UUID = Field(description="Card identifier.", examples=["11111111-1111-1111-1111-111111111111"])
    source_text: str = Field(description="Original phrase.", examples=["good luck"])
    translated_text: str = Field(description="Translated phrase.", examples=["buena suerte"])
    source_lang: str = Field(description="Source language code.", examples=["en"])
    target_lang: str = Field(description="Target language code.", examples=["es"])
    learning_status: LearningStatus = Field(description="Learning status.", examples=["active"])
    provider_name: str = Field(description="Translation provider name.", examples=["mock"])
    scheduled_reviews: list[ScheduledReviewResponse] = Field(
        description="Review schedule for both directions."
    )


class HistoryItemResponse(BaseModel):
    """Single history row returned by the API."""

    card_id: UUID = Field(description="Card identifier.", examples=["11111111-1111-1111-1111-111111111111"])
    source_text: str = Field(description="Original phrase.", examples=["good luck"])
    translated_text: str = Field(description="Translated phrase.", examples=["buena suerte"])
    source_lang: str = Field(description="Source language code.", examples=["en"])
    target_lang: str = Field(description="Target language code.", examples=["es"])
    created_at: datetime = Field(description="Creation timestamp.", examples=["2026-03-28T12:00:00Z"])
    learning_status: LearningStatus = Field(description="Learning status.", examples=["active"])


class ToggleLearningRequest(BaseModel):
    """Payload for learning enable/disable switch."""

    user_id: int = Field(description="Telegram user id.", examples=[123456789])
    learning_enabled: bool = Field(
        description="Whether the card should remain in learning.",
        examples=[False],
    )


class LearningStateResponse(BaseModel):
    """Minimal card state after toggling learning."""

    card_id: UUID = Field(description="Card identifier.", examples=["11111111-1111-1111-1111-111111111111"])
    learning_status: LearningStatus = Field(description="Current learning status.", examples=["not_learning"])


class DueReviewResponse(BaseModel):
    """Due review prompt."""

    card_id: UUID = Field(description="Card identifier.", examples=["11111111-1111-1111-1111-111111111111"])
    direction: ReviewDirection = Field(description="Quiz direction.", examples=["forward"])
    prompt_text: str = Field(description="Text shown to the learner.", examples=["good luck"])
    due_at: datetime = Field(description="Due timestamp.", examples=["2026-03-30T12:00:00Z"])
    step_index: int = Field(description="Current review step.", examples=[0])


class ReviewAnswerRequest(BaseModel):
    """Payload for a manual quiz answer."""

    user_id: int = Field(description="Telegram user id.", examples=[123456789])
    direction: ReviewDirection = Field(description="Quiz direction.", examples=["forward"])
    answer_text: str = Field(description="Manual answer entered by the user.", examples=["buena suerte"])


class ReviewAnswerResponse(BaseModel):
    """Result of a quiz answer."""

    card_id: UUID = Field(description="Card identifier.", examples=["11111111-1111-1111-1111-111111111111"])
    direction: ReviewDirection = Field(description="Quiz direction.", examples=["forward"])
    outcome: ReviewOutcome = Field(description="Review result.", examples=["correct"])
    expected_answer: str = Field(description="Expected answer used for evaluation.", examples=["buena suerte"])
    provided_answer: str = Field(description="User answer.", examples=["buena suerte"])
    step_index: int = Field(description="Updated step index.", examples=[1])
    next_review_at: datetime | None = Field(
        description="Next due datetime or null if learned.",
        examples=["2026-04-02T12:00:00Z"],
    )
    learning_status: LearningStatus = Field(description="Card learning status.", examples=["active"])


class ProgressResponse(BaseModel):
    """Aggregated user progress."""

    total_cards: int = Field(description="Total number of cards.", examples=[12])
    active_cards: int = Field(description="Cards still in learning.", examples=[8])
    learned_cards: int = Field(description="Cards fully learned.", examples=[2])
    not_learning_cards: int = Field(description="Cards excluded from learning.", examples=[2])
    due_reviews: int = Field(description="Reviews currently due.", examples=[3])
    completed_review_tracks: int = Field(description="Completed directional tracks.", examples=[7])
    total_review_tracks: int = Field(description="Total directional tracks.", examples=[24])


class SettingsResponse(BaseModel):
    """User settings payload."""

    user_id: int = Field(description="Telegram user id.", examples=[123456789])
    default_source_lang: str = Field(description="Default source language.", examples=["en"])
    default_target_lang: str = Field(description="Default target language.", examples=["es"])
    timezone: str = Field(description="IANA timezone name.", examples=["Europe/Moscow"])
    notification_time_local: time = Field(
        description="Preferred local notification time.",
        examples=["09:00:00"],
    )
    notifications_enabled: bool = Field(
        description="Whether notifications are enabled.",
        examples=[True],
    )


class UpdateSettingsRequest(BaseModel):
    """Payload for updating settings."""

    user_id: int = Field(description="Telegram user id.", examples=[123456789])
    default_source_lang: str = Field(description="Default source language code.", examples=["en"])
    default_target_lang: str = Field(description="Default target language code.", examples=["es"])
    timezone: str = Field(description="IANA timezone name.", examples=["Europe/Moscow"])
    notification_time_local: time = Field(
        description="Preferred local notification time.",
        examples=["09:00:00"],
    )
    notifications_enabled: bool = Field(
        description="Whether notifications should be sent.",
        examples=[True],
    )


def build_api_router(container: ApplicationContainer) -> APIRouter:
    """Create an API router bound to the application container."""

    router = APIRouter(tags=["spaced-repetition-bot"])

    @router.get(
        "/health",
        response_model=HealthResponse,
        summary="Health check",
        description="Return basic health information for the service.",
        responses={
            200: {
                "description": "Service is healthy.",
                "content": {"application/json": {"example": {"status": "ok", "version": "0.1.0"}}},
            }
        },
    )
    def health_check() -> HealthResponse:
        return HealthResponse(status="ok", version=container.config.app_version)

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
        )
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
                ScheduledReviewResponse.model_validate(item, from_attributes=True)
                for item in result.scheduled_reviews
            ],
        )

    @router.get(
        "/history",
        response_model=list[HistoryItemResponse],
        summary="Get translation history",
        description="Return recent translation history for a user.",
        responses={
            200: {
                "description": "Recent history rows.",
                "content": {
                    "application/json": {
                        "example": [
                            {
                                "card_id": "11111111-1111-1111-1111-111111111111",
                                "source_text": "good luck",
                                "translated_text": "good luck (es)",
                                "source_lang": "en",
                                "target_lang": "es",
                                "created_at": "2026-03-28T12:00:00Z",
                                "learning_status": "active",
                            }
                        ]
                    }
                },
            }
        },
    )
    def get_history(
        user_id: int = Query(description="Telegram user id.", examples=[123456789]),
        limit: int = Query(
            default=20,
            ge=1,
            le=100,
            description="Maximum number of history rows to return.",
            examples=[20],
        ),
    ) -> list[HistoryItemResponse]:
        items = container.get_history.execute(GetHistoryQuery(user_id=user_id, limit=limit))
        return [HistoryItemResponse.model_validate(item, from_attributes=True) for item in items]

    @router.patch(
        "/cards/{card_id}/learning",
        response_model=LearningStateResponse,
        summary="Enable or disable learning",
        description="Toggle whether a card participates in future reviews.",
        responses={
            200: {
                "description": "Learning state updated.",
                "content": {
                    "application/json": {
                        "example": {
                            "card_id": "11111111-1111-1111-1111-111111111111",
                            "learning_status": "not_learning",
                        }
                    }
                },
            },
            404: {
                "description": "Card not found.",
                "content": {"application/json": {"example": {"detail": "Card not found."}}},
            },
        },
    )
    def toggle_learning(
        payload: ToggleLearningRequest = Body(
            description="Learning toggle request.",
            examples=[{"user_id": 123456789, "learning_enabled": False}],
        ),
        card_id: UUID = Path(description="Card identifier."),
    ) -> LearningStateResponse:
        try:
            card = container.toggle_learning.execute(
                ToggleLearningCommand(
                    user_id=payload.user_id,
                    card_id=card_id,
                    learning_enabled=payload.learning_enabled,
                )
            )
        except ApplicationError as error:
            raise to_http_exception(error) from error
        return LearningStateResponse(card_id=card.id, learning_status=card.learning_status)

    @router.get(
        "/reviews/due",
        response_model=list[DueReviewResponse],
        summary="Get due reviews",
        description="Return all reviews that are due for a user right now.",
        responses={
            200: {
                "description": "List of due reviews.",
                "content": {
                    "application/json": {
                        "example": [
                            {
                                "card_id": "11111111-1111-1111-1111-111111111111",
                                "direction": "forward",
                                "prompt_text": "good luck",
                                "due_at": "2026-03-30T12:00:00Z",
                                "step_index": 0,
                            }
                        ]
                    }
                },
            }
        },
    )
    def get_due_reviews(
        user_id: int = Query(description="Telegram user id.", examples=[123456789]),
    ) -> list[DueReviewResponse]:
        items = container.get_due_reviews.execute(user_id=user_id)
        return [DueReviewResponse.model_validate(item, from_attributes=True) for item in items]

    @router.post(
        "/reviews/{card_id}/answer",
        response_model=ReviewAnswerResponse,
        summary="Submit a review answer",
        description="Evaluate a manual answer and update the review schedule.",
        responses={
            200: {
                "description": "Answer processed.",
                "content": {
                    "application/json": {
                        "example": {
                            "card_id": "11111111-1111-1111-1111-111111111111",
                            "direction": "forward",
                            "outcome": "correct",
                            "expected_answer": "buena suerte",
                            "provided_answer": "buena suerte",
                            "step_index": 1,
                            "next_review_at": "2026-04-02T12:00:00Z",
                            "learning_status": "active",
                        }
                    }
                },
            },
            400: {
                "description": "Review is not available.",
                "content": {"application/json": {"example": {"detail": "Review is not due."}}},
            },
            404: {
                "description": "Card not found.",
                "content": {"application/json": {"example": {"detail": "Card not found."}}},
            },
        },
    )
    def submit_review_answer(
        card_id: UUID = Path(description="Card identifier."),
        payload: ReviewAnswerRequest = Body(
            description="Review answer payload.",
            examples=[{"user_id": 123456789, "direction": "forward", "answer_text": "buena suerte"}],
        ),
    ) -> ReviewAnswerResponse:
        try:
            result = container.submit_review_answer.execute(
                SubmitReviewAnswerCommand(
                    user_id=payload.user_id,
                    card_id=card_id,
                    direction=payload.direction,
                    answer_text=payload.answer_text,
                )
            )
        except ApplicationError as error:
            raise to_http_exception(error) from error
        return ReviewAnswerResponse.model_validate(result, from_attributes=True)

    @router.get(
        "/progress",
        response_model=ProgressResponse,
        summary="Get learning progress",
        description="Return aggregated progress metrics for a user.",
        responses={
            200: {
                "description": "Aggregated progress metrics.",
                "content": {
                    "application/json": {
                        "example": {
                            "total_cards": 12,
                            "active_cards": 8,
                            "learned_cards": 2,
                            "not_learning_cards": 2,
                            "due_reviews": 3,
                            "completed_review_tracks": 7,
                            "total_review_tracks": 24,
                        }
                    }
                },
            }
        },
    )
    def get_progress(
        user_id: int = Query(description="Telegram user id.", examples=[123456789]),
    ) -> ProgressResponse:
        result = container.get_user_progress.execute(GetUserProgressQuery(user_id=user_id))
        return ProgressResponse.model_validate(result, from_attributes=True)

    @router.get(
        "/settings",
        response_model=SettingsResponse,
        summary="Get user settings",
        description="Return current user settings or defaults.",
        responses={
            200: {
                "description": "User settings.",
                "content": {
                    "application/json": {
                        "example": {
                            "user_id": 123456789,
                            "default_source_lang": "en",
                            "default_target_lang": "es",
                            "timezone": "Europe/Moscow",
                            "notification_time_local": "09:00:00",
                            "notifications_enabled": True,
                        }
                    }
                },
            }
        },
    )
    def get_settings(
        user_id: int = Query(description="Telegram user id.", examples=[123456789]),
    ) -> SettingsResponse:
        result = container.get_settings.execute(GetSettingsQuery(user_id=user_id))
        return SettingsResponse.model_validate(result, from_attributes=True)

    @router.put(
        "/settings",
        response_model=SettingsResponse,
        summary="Update user settings",
        description="Persist settings that influence translation defaults and notifications.",
        responses={
            200: {
                "description": "Settings updated.",
                "content": {
                    "application/json": {
                        "example": {
                            "user_id": 123456789,
                            "default_source_lang": "en",
                            "default_target_lang": "es",
                            "timezone": "Europe/Moscow",
                            "notification_time_local": "09:00:00",
                            "notifications_enabled": True,
                        }
                    }
                },
            }
        },
    )
    def update_settings(
        payload: UpdateSettingsRequest = Body(
            description="Settings payload.",
            examples=[
                {
                    "user_id": 123456789,
                    "default_source_lang": "en",
                    "default_target_lang": "es",
                    "timezone": "Europe/Moscow",
                    "notification_time_local": "09:00:00",
                    "notifications_enabled": True,
                }
            ],
        )
    ) -> SettingsResponse:
        result = container.update_settings.execute(
            UpdateSettingsCommand(
                user_id=payload.user_id,
                default_source_lang=payload.default_source_lang,
                default_target_lang=payload.default_target_lang,
                timezone=payload.timezone,
                notification_time_local=payload.notification_time_local,
                notifications_enabled=payload.notifications_enabled,
            )
        )
        return SettingsResponse.model_validate(result, from_attributes=True)

    return router


def to_http_exception(error: ApplicationError) -> HTTPException:
    """Map application errors to HTTP errors."""

    if isinstance(error, CardNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Card not found.",
        )
    if isinstance(error, LearningDisabledError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Card is excluded from learning.",
        )
    if isinstance(error, ReviewNotAvailableError):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Review is not due.",
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unexpected application error.",
    )
