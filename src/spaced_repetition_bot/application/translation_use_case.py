"""Use case for phrase translation."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from spaced_repetition_bot.application.dto_translation import (
    TranslatePhraseCommand,
    TranslationResult,
)
from spaced_repetition_bot.application.ports import (
    Clock,
    PhraseRepository,
    SettingsRepository,
    TranslationProvider,
)
from spaced_repetition_bot.application.use_case_common import (
    default_settings,
    map_scheduled_review,
)
from spaced_repetition_bot.domain.enums import LearningStatus
from spaced_repetition_bot.domain.models import PhraseCard
from spaced_repetition_bot.domain.policies import SpacedRepetitionPolicy


@dataclass(slots=True)
class TranslatePhraseUseCase:
    """Translate text and create a learning card."""

    phrase_repository: PhraseRepository
    settings_repository: SettingsRepository
    translation_provider: TranslationProvider
    spaced_repetition_policy: SpacedRepetitionPolicy
    clock: Clock

    def execute(self, command: TranslatePhraseCommand) -> TranslationResult:
        settings = self.settings_repository.get(
            command.user_id
        ) or default_settings(command.user_id)
        source_lang = command.source_lang or settings.default_source_lang
        target_lang = command.target_lang or settings.default_target_lang
        translated = self.translation_provider.translate(
            text=command.text,
            source_lang=source_lang,
            target_lang=target_lang,
        )
        now = self.clock.now()
        learning_status = self._learning_status(command.learn)
        card = PhraseCard(
            id=uuid4(),
            user_id=command.user_id,
            source_text=command.text,
            target_text=translated.translated_text,
            source_lang=source_lang,
            target_lang=target_lang,
            created_at=now,
            learning_status=learning_status,
            review_tracks=self.spaced_repetition_policy.initialize_tracks(now),
            archived_reason=self._archived_reason(command.learn),
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
            scheduled_reviews=tuple(
                map_scheduled_review(track)
                for track in stored_card.review_tracks
            ),
        )

    @staticmethod
    def _learning_status(learn: bool) -> LearningStatus:
        if learn:
            return LearningStatus.ACTIVE
        return LearningStatus.NOT_LEARNING

    @staticmethod
    def _archived_reason(learn: bool) -> str | None:
        if learn:
            return None
        return "created_without_learning"
