"""Application use cases."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from spaced_repetition_bot.application.dtos import (
    DueReviewItem,
    GetHistoryQuery,
    GetSettingsQuery,
    GetUserProgressQuery,
    HistoryItem,
    ReviewAnswerResult,
    ScheduledReviewItem,
    SubmitReviewAnswerCommand,
    ToggleLearningCommand,
    TranslatePhraseCommand,
    TranslationResult,
    UpdateSettingsCommand,
    UserProgressSnapshot,
    UserSettingsSnapshot,
)
from spaced_repetition_bot.application.errors import (
    CardNotFoundError,
    LearningDisabledError,
    ReviewNotAvailableError,
)
from spaced_repetition_bot.application.ports import (
    Clock,
    PhraseRepository,
    SettingsRepository,
    TranslationProvider,
)
from spaced_repetition_bot.domain.enums import LearningStatus, ReviewOutcome
from spaced_repetition_bot.domain.models import PhraseCard, UserSettings
from spaced_repetition_bot.domain.policies import (
    AnswerEvaluationPolicy,
    SpacedRepetitionPolicy,
)


def default_settings(user_id: int) -> UserSettings:
    """Return default user settings."""

    return UserSettings(user_id=user_id)


def map_settings_snapshot(settings: UserSettings) -> UserSettingsSnapshot:
    """Convert settings to an external DTO."""

    return UserSettingsSnapshot(
        user_id=settings.user_id,
        default_source_lang=settings.default_source_lang,
        default_target_lang=settings.default_target_lang,
        timezone=settings.timezone,
        notification_time_local=settings.notification_time_local,
        notifications_enabled=settings.notifications_enabled,
    )


def map_scheduled_review(track) -> ScheduledReviewItem:
    """Convert a track to a schedule DTO."""

    return ScheduledReviewItem(
        direction=track.direction,
        step_index=track.step_index,
        next_review_at=track.next_review_at,
        completed=track.is_completed,
    )


@dataclass(slots=True)
class TranslatePhraseUseCase:
    """Translate text and create a learning card."""

    phrase_repository: PhraseRepository
    settings_repository: SettingsRepository
    translation_provider: TranslationProvider
    spaced_repetition_policy: SpacedRepetitionPolicy
    clock: Clock

    def execute(self, command: TranslatePhraseCommand) -> TranslationResult:
        settings = self.settings_repository.get(command.user_id) or default_settings(
            command.user_id
        )
        source_lang = command.source_lang or settings.default_source_lang
        target_lang = command.target_lang or settings.default_target_lang
        translated = self.translation_provider.translate(
            text=command.text,
            source_lang=source_lang,
            target_lang=target_lang,
        )
        now = self.clock.now()
        tracks = self.spaced_repetition_policy.initialize_tracks(now)
        learning_status = LearningStatus.ACTIVE if command.learn else LearningStatus.NOT_LEARNING
        card = PhraseCard(
            id=uuid4(),
            user_id=command.user_id,
            source_text=command.text,
            target_text=translated.translated_text,
            source_lang=source_lang,
            target_lang=target_lang,
            created_at=now,
            learning_status=learning_status,
            review_tracks=tracks,
            archived_reason=None if command.learn else "created_without_learning",
        )
        stored_card = self.phrase_repository.add(card)
        return TranslationResult(
            card_id=stored_card.id,
            source_text=stored_card.source_text,
            translated_text=stored_card.target_text,
            source_lang=stored_card.source_lang,
            target_lang=stored_card.target_lang,
            learning_status=stored_card.learning_status,
            provider_name=translated.provider_name,
            scheduled_reviews=tuple(map_scheduled_review(track) for track in stored_card.review_tracks),
        )


@dataclass(slots=True)
class GetHistoryUseCase:
    """Return user translation history."""

    phrase_repository: PhraseRepository

    def execute(self, query: GetHistoryQuery) -> list[HistoryItem]:
        cards = sorted(
            self.phrase_repository.list_by_user(query.user_id),
            key=lambda card: card.created_at,
            reverse=True,
        )
        return [
            HistoryItem(
                card_id=card.id,
                source_text=card.source_text,
                translated_text=card.target_text,
                source_lang=card.source_lang,
                target_lang=card.target_lang,
                created_at=card.created_at,
                learning_status=card.learning_status,
            )
            for card in cards[: query.limit]
        ]


@dataclass(slots=True)
class ToggleLearningUseCase:
    """Enable or disable learning for a card."""

    phrase_repository: PhraseRepository

    def execute(self, command: ToggleLearningCommand) -> PhraseCard:
        card = self._load_user_card(command.card_id, command.user_id)
        updated_card = card.enable_learning() if command.learning_enabled else card.disable_learning()
        return self.phrase_repository.save(updated_card)

    def _load_user_card(self, card_id, user_id: int) -> PhraseCard:
        card = self.phrase_repository.get(card_id)
        if card is None or card.user_id != user_id:
            raise CardNotFoundError(f"Card '{card_id}' was not found for user '{user_id}'.")
        return card


@dataclass(slots=True)
class GetDueReviewsUseCase:
    """Return due review prompts."""

    phrase_repository: PhraseRepository
    clock: Clock

    def execute(self, user_id: int) -> list[DueReviewItem]:
        now = self.clock.now()
        due_reviews: list[DueReviewItem] = []
        for card in self.phrase_repository.list_by_user(user_id):
            if card.learning_status is not LearningStatus.ACTIVE:
                continue
            for track in card.review_tracks:
                if not track.is_due(now):
                    continue
                due_reviews.append(
                    DueReviewItem(
                        card_id=card.id,
                        direction=track.direction,
                        prompt_text=card.prompt_for(track.direction),
                        due_at=track.next_review_at,
                        step_index=track.step_index,
                    )
                )
        return sorted(due_reviews, key=lambda item: item.due_at)


@dataclass(slots=True)
class SubmitReviewAnswerUseCase:
    """Evaluate an answer and update the schedule."""

    phrase_repository: PhraseRepository
    spaced_repetition_policy: SpacedRepetitionPolicy
    answer_evaluation_policy: AnswerEvaluationPolicy
    clock: Clock

    def execute(self, command: SubmitReviewAnswerCommand) -> ReviewAnswerResult:
        card = self._load_user_card(command.card_id, command.user_id)
        if card.learning_status is LearningStatus.NOT_LEARNING:
            raise LearningDisabledError(f"Card '{card.id}' is excluded from learning.")
        track = card.track_for(command.direction)
        now = self.clock.now()
        if not track.is_due(now):
            raise ReviewNotAvailableError(
                f"Review for card '{card.id}' and direction '{command.direction}' is not due."
            )
        expected = card.expected_answer_for(command.direction)
        outcome = self._evaluate(expected=expected, provided=command.answer_text)
        updated_track = self.spaced_repetition_policy.apply_outcome(
            track=track,
            now=now,
            outcome=outcome,
        )
        updated_card = self.phrase_repository.save(card.replace_track(updated_track))
        return ReviewAnswerResult(
            card_id=updated_card.id,
            direction=command.direction,
            outcome=outcome,
            expected_answer=expected,
            provided_answer=command.answer_text,
            step_index=updated_track.step_index,
            next_review_at=updated_track.next_review_at,
            learning_status=updated_card.learning_status,
        )

    def _evaluate(self, expected: str, provided: str) -> ReviewOutcome:
        if self.answer_evaluation_policy.is_correct(expected=expected, provided=provided):
            return ReviewOutcome.CORRECT
        return ReviewOutcome.INCORRECT

    def _load_user_card(self, card_id, user_id: int) -> PhraseCard:
        card = self.phrase_repository.get(card_id)
        if card is None or card.user_id != user_id:
            raise CardNotFoundError(f"Card '{card_id}' was not found for user '{user_id}'.")
        return card


@dataclass(slots=True)
class GetUserProgressUseCase:
    """Aggregate user progress."""

    phrase_repository: PhraseRepository
    clock: Clock

    def execute(self, query: GetUserProgressQuery) -> UserProgressSnapshot:
        cards = self.phrase_repository.list_by_user(query.user_id)
        now = self.clock.now()
        total_review_tracks = sum(len(card.review_tracks) for card in cards)
        completed_review_tracks = sum(
            track.is_completed for card in cards for track in card.review_tracks
        )
        due_reviews = sum(
            track.is_due(now)
            for card in cards
            if card.learning_status is LearningStatus.ACTIVE
            for track in card.review_tracks
        )
        return UserProgressSnapshot(
            total_cards=len(cards),
            active_cards=sum(card.learning_status is LearningStatus.ACTIVE for card in cards),
            learned_cards=sum(card.learning_status is LearningStatus.LEARNED for card in cards),
            not_learning_cards=sum(
                card.learning_status is LearningStatus.NOT_LEARNING for card in cards
            ),
            due_reviews=due_reviews,
            completed_review_tracks=completed_review_tracks,
            total_review_tracks=total_review_tracks,
        )


@dataclass(slots=True)
class GetSettingsUseCase:
    """Return user settings, creating defaults on the fly."""

    settings_repository: SettingsRepository

    def execute(self, query: GetSettingsQuery) -> UserSettingsSnapshot:
        settings = self.settings_repository.get(query.user_id) or default_settings(query.user_id)
        return map_settings_snapshot(settings)


@dataclass(slots=True)
class UpdateSettingsUseCase:
    """Persist updated user settings."""

    settings_repository: SettingsRepository

    def execute(self, command: UpdateSettingsCommand) -> UserSettingsSnapshot:
        settings = UserSettings(
            user_id=command.user_id,
            default_source_lang=command.default_source_lang,
            default_target_lang=command.default_target_lang,
            timezone=command.timezone,
            notification_time_local=command.notification_time_local,
            notifications_enabled=command.notifications_enabled,
        )
        stored = self.settings_repository.save(settings)
        return map_settings_snapshot(stored)
