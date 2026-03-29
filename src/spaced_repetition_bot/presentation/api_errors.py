"""HTTP error mapping for the API layer."""

from __future__ import annotations

from fastapi import HTTPException, status

from spaced_repetition_bot.application.errors import (
    ApplicationError,
    CardNotFoundError,
    InvalidSettingsError,
    LearningDisabledError,
    ReviewNotAvailableError,
    TranslationProviderError,
)


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
    if isinstance(error, InvalidSettingsError):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )
    if isinstance(error, TranslationProviderError):
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Translation provider is unavailable.",
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unexpected application error.",
    )
