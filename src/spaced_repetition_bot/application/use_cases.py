"""Application use cases."""

from __future__ import annotations

from dataclasses import dataclass, replace
import re
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from spaced_repetition_bot.application.dtos import (
    ActiveQuizAnswerResult,
    DueReviewItem,
    GetHistoryQuery,
    GetSettingsQuery,
    GetUserProgressQuery,
    HistoryItem,
    QuizSessionStartResult,
    QuizSessionPrompt,
    QuizSessionSummary,
    ReviewAnswerResult,
    ScheduledReviewItem,
    SkipQuizResult,
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
    InvalidSettingsError,
    LearningDisabledError,
    QuizSessionNotFoundError,
    ReviewNotAvailableError,
)
from spaced_repetition_bot.application.ports import (
    Clock,
    PhraseRepository,
    QuizSessionRepository,
    SettingsRepository,
    TranslationProvider,
)
from spaced_repetition_bot.domain.enums import (
    LearningStatus,
    ReviewDirection,
    ReviewOutcome,
)
from spaced_repetition_bot.domain.models import (
    PhraseCard,
    QuizReviewPointer,
    TelegramQuizSession,
    UserSettings,
)
from spaced_repetition_bot.domain.policies import (
    AnswerEvaluationPolicy,
    NormalizedTextAnswerPolicy,
    SpacedRepetitionPolicy,
)

LANGUAGE_CODE_PATTERN = re.compile(r"^[a-z]{2,3}(?:-[a-z0-9]{2,8})?$")
QUIZ_SESSION_LIMIT = 10


def default_settings(user_id: int) -> UserSettings:
    """Return default user settings."""

    return UserSettings(user_id=user_id)


def map_settings_snapshot(settings: UserSettings) -> UserSettingsSnapshot:
    """Convert settings to an external DTO."""

    return UserSettingsSnapshot(
        user_id=settings.user_id,
        default_source_lang=settings.default_source_lang,
        default_target_lang=settings.default_target_lang,
        default_translation_direction=settings.default_translation_direction,
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


def normalize_text(value: str) -> str:
    """Normalize text for user-facing translation heuristics."""

    return NormalizedTextAnswerPolicy.normalize(value)


def normalize_language_code(language_code: str | None) -> str | None:
    """Normalize provider language codes for comparisons."""

    if language_code is None:
        return None
    return language_code.strip().replace("_", "-").casefold()


def build_quiz_prompt(
    card: PhraseCard,
    direction: ReviewDirection,
    *,
    session_position: int = 1,
    total_prompts: int = 1,
) -> QuizSessionPrompt:
    """Build a Telegram quiz prompt from a card."""

    track = card.track_for(direction)
    return QuizSessionPrompt(
        card_id=card.id,
        direction=direction,
        prompt_text=card.prompt_for(direction),
        expected_answer=card.expected_answer_for(direction),
        step_index=track.step_index,
        session_position=session_position,
        total_prompts=total_prompts,
    )


def find_existing_translation_card(
    phrase_repository: PhraseRepository,
    *,
    user_id: int,
    source_text: str,
    translated_text: str,
    source_lang: str,
    target_lang: str,
) -> PhraseCard | None:
    """Return an existing matching card for a user if present."""

    return phrase_repository.find_matching_card(
        user_id=user_id,
        source_text=source_text,
        translated_text=translated_text,
        source_lang=source_lang,
        target_lang=target_lang,
    )


def list_due_reviews(
    phrase_repository: PhraseRepository,
    user_id: int,
    now,
) -> list[DueReviewItem]:
    """Return sorted due reviews for a user."""

    return phrase_repository.list_due_reviews(user_id=user_id, now=now)


def mix_due_reviews(due_reviews: list[DueReviewItem]) -> list[DueReviewItem]:
    """Spread reviews from the same card apart when possible."""

    grouped_reviews: dict[str, list[DueReviewItem]] = {}
    card_order: list[str] = []
    for item in due_reviews:
        card_key = str(item.card_id)
        if card_key not in grouped_reviews:
            grouped_reviews[card_key] = []
            card_order.append(card_key)
        grouped_reviews[card_key].append(item)
    mixed: list[DueReviewItem] = []
    while True:
        round_items = 0
        for card_key in card_order:
            reviews = grouped_reviews[card_key]
            if not reviews:
                continue
            mixed.append(reviews.pop(0))
            round_items += 1
        if round_items == 0:
            return mixed


def load_user_card(
    phrase_repository: PhraseRepository,
    card_id,
    user_id: int,
) -> PhraseCard:
    """Load a card and ensure it belongs to the user."""

    card = phrase_repository.get(card_id)
    if card is None or card.user_id != user_id:
        raise CardNotFoundError(
            f"Card '{card_id}' was not found for user '{user_id}'."
        )
    return card


def build_quiz_summary(
    *,
    total_prompts: int,
    answered_prompts: int,
    correct_prompts: int,
    incorrect_prompts: int,
    remaining_due_reviews: int,
) -> QuizSessionSummary:
    """Create a summary DTO for a completed quiz session."""

    return QuizSessionSummary(
        total_prompts=total_prompts,
        answered_prompts=answered_prompts,
        correct_prompts=correct_prompts,
        incorrect_prompts=incorrect_prompts,
        remaining_due_reviews=remaining_due_reviews,
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
        settings = self._get_or_create_settings(command.user_id)
        direction = command.direction or settings.default_translation_direction
        source_lang, target_lang = settings.translation_pair_for(direction)
        translated = self.translation_provider.translate(
            text=command.text,
            source_lang=source_lang,
            target_lang=target_lang,
        )
        warning_state = self._build_warning_state(
            source_text=command.text,
            translated_text=translated.translated_text,
            detected_source_lang=translated.detected_source_lang,
            expected_source_lang=source_lang,
        )
        if self._should_return_warning_preview(
            warning_state=warning_state,
            command=command,
        ):
            return self._build_preview_result(
                command=command,
                translated_text=translated.translated_text,
                direction=direction,
                source_lang=source_lang,
                target_lang=target_lang,
                provider_name=translated.provider_name,
                detected_source_lang=warning_state.detected_source_lang,
                is_identity_translation=warning_state.is_identity_translation,
                has_pair_warning=warning_state.has_pair_warning,
            )
        existing_card = find_existing_translation_card(
            self.phrase_repository,
            user_id=command.user_id,
            source_text=command.text,
            translated_text=translated.translated_text,
            source_lang=source_lang,
            target_lang=target_lang,
        )
        if existing_card is not None:
            return self._build_saved_result(
                card=existing_card,
                direction=direction,
                provider_name=translated.provider_name,
                detected_source_lang=warning_state.detected_source_lang,
                is_identity_translation=warning_state.is_identity_translation,
                has_pair_warning=warning_state.has_pair_warning,
                already_saved=True,
            )
        stored_card = self.phrase_repository.add(
            self._build_new_card(
                command=command,
                translated_text=translated.translated_text,
                source_lang=source_lang,
                target_lang=target_lang,
            )
        )
        return self._build_saved_result(
            card=stored_card,
            direction=direction,
            provider_name=translated.provider_name,
            detected_source_lang=warning_state.detected_source_lang,
            is_identity_translation=warning_state.is_identity_translation,
            has_pair_warning=warning_state.has_pair_warning,
            already_saved=False,
        )

    def _get_or_create_settings(self, user_id: int) -> UserSettings:
        settings = self.settings_repository.get(user_id)
        if settings is not None:
            return settings
        return self.settings_repository.save(default_settings(user_id))

    def _build_warning_state(
        self,
        *,
        source_text: str,
        translated_text: str,
        detected_source_lang: str | None,
        expected_source_lang: str,
    ) -> TranslationWarningState:
        normalized_detected = normalize_language_code(detected_source_lang)
        is_identity_translation = (
            normalize_text(source_text) == normalize_text(translated_text)
        )
        has_language_mismatch = (
            normalized_detected is not None
            and normalized_detected
            != normalize_language_code(expected_source_lang)
        )
        return TranslationWarningState(
            detected_source_lang=normalized_detected,
            is_identity_translation=is_identity_translation,
            has_pair_warning=(
                is_identity_translation or has_language_mismatch
            ),
        )

    def _should_return_warning_preview(
        self,
        *,
        warning_state: TranslationWarningState,
        command: TranslatePhraseCommand,
    ) -> bool:
        return (
            warning_state.has_pair_warning
            and not command.save_with_warning
        )

    def _build_new_card(
        self,
        *,
        command: TranslatePhraseCommand,
        translated_text: str,
        source_lang: str,
        target_lang: str,
    ) -> PhraseCard:
        now = self.clock.now()
        learning_status, archived_reason = self._resolve_learning_state(
            command.learn
        )
        return PhraseCard(
            id=uuid4(),
            user_id=command.user_id,
            source_text=command.text,
            target_text=translated_text,
            source_lang=source_lang,
            target_lang=target_lang,
            created_at=now,
            learning_status=learning_status,
            review_tracks=self.spaced_repetition_policy.initialize_tracks(now),
            archived_reason=archived_reason,
        )

    def _resolve_learning_state(
        self,
        should_learn: bool,
    ) -> tuple[LearningStatus, str | None]:
        if should_learn:
            return LearningStatus.ACTIVE, None
        return LearningStatus.NOT_LEARNING, "created_without_learning"

    def _build_preview_result(
        self,
        *,
        command: TranslatePhraseCommand,
        translated_text: str,
        direction: ReviewDirection,
        source_lang: str,
        target_lang: str,
        provider_name: str,
        detected_source_lang: str | None,
        is_identity_translation: bool,
        has_pair_warning: bool,
    ) -> TranslationResult:
        return TranslationResult(
            card_id=None,
            source_text=command.text,
            translated_text=translated_text,
            direction=direction,
            source_lang=source_lang,
            target_lang=target_lang,
            learning_status=None,
            provider_name=provider_name,
            detected_source_lang=detected_source_lang,
            is_identity_translation=is_identity_translation,
            has_pair_warning=has_pair_warning,
            saved=False,
            already_saved=False,
            scheduled_reviews=(),
        )

    def _build_saved_result(
        self,
        *,
        card: PhraseCard,
        direction: ReviewDirection,
        provider_name: str,
        detected_source_lang: str | None,
        is_identity_translation: bool,
        has_pair_warning: bool,
        already_saved: bool,
    ) -> TranslationResult:
        return TranslationResult(
            card_id=card.id,
            source_text=card.source_text,
            translated_text=card.target_text,
            direction=direction,
            source_lang=card.source_lang,
            target_lang=card.target_lang,
            learning_status=card.learning_status,
            provider_name=provider_name,
            detected_source_lang=detected_source_lang,
            is_identity_translation=is_identity_translation,
            has_pair_warning=has_pair_warning,
            saved=True,
            already_saved=already_saved,
            scheduled_reviews=tuple(
                map_scheduled_review(track) for track in card.review_tracks
            ),
        )


@dataclass(frozen=True, slots=True)
class TranslationWarningState:
    """Derived translation warning details for the current request."""

    detected_source_lang: str | None
    is_identity_translation: bool
    has_pair_warning: bool


@dataclass(slots=True)
class GetHistoryUseCase:
    """Return user translation history."""

    phrase_repository: PhraseRepository

    def execute(self, query: GetHistoryQuery) -> list[HistoryItem]:
        return self.phrase_repository.list_history_by_user(
            user_id=query.user_id,
            limit=query.limit,
        )


@dataclass(slots=True)
class ToggleLearningUseCase:
    """Enable or disable learning for a card."""

    phrase_repository: PhraseRepository

    def execute(self, command: ToggleLearningCommand) -> PhraseCard:
        card = load_user_card(
            self.phrase_repository, command.card_id, command.user_id
        )
        updated_card = (
            card.enable_learning()
            if command.learning_enabled
            else card.disable_learning()
        )
        return self.phrase_repository.save(updated_card)


@dataclass(slots=True)
class GetDueReviewsUseCase:
    """Return due review prompts."""

    phrase_repository: PhraseRepository
    clock: Clock

    def execute(self, user_id: int) -> list[DueReviewItem]:
        return list_due_reviews(
            phrase_repository=self.phrase_repository,
            user_id=user_id,
            now=self.clock.now(),
        )


@dataclass(slots=True)
class SubmitReviewAnswerUseCase:
    """Evaluate an answer and update the schedule."""

    phrase_repository: PhraseRepository
    spaced_repetition_policy: SpacedRepetitionPolicy
    answer_evaluation_policy: AnswerEvaluationPolicy
    clock: Clock

    def execute(
        self, command: SubmitReviewAnswerCommand
    ) -> ReviewAnswerResult:
        card = load_user_card(
            self.phrase_repository, command.card_id, command.user_id
        )
        if card.learning_status is LearningStatus.NOT_LEARNING:
            raise LearningDisabledError(
                f"Card '{card.id}' is excluded from learning."
            )
        track = card.track_for(command.direction)
        now = self.clock.now()
        if not track.is_due(now):
            raise ReviewNotAvailableError(
                "Review for card "
                f"'{card.id}' and direction '{command.direction}' "
                "is not due."
            )
        expected = card.expected_answer_for(command.direction)
        outcome = self._evaluate(
            expected=expected, provided=command.answer_text
        )
        updated_track = self.spaced_repetition_policy.apply_outcome(
            track=track,
            now=now,
            outcome=outcome,
        )
        updated_card = self.phrase_repository.save(
            card.replace_track(updated_track)
        )
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
        if self.answer_evaluation_policy.is_correct(
            expected=expected, provided=provided
        ):
            return ReviewOutcome.CORRECT
        return ReviewOutcome.INCORRECT


@dataclass(slots=True)
class GetUserProgressUseCase:
    """Aggregate user progress."""

    phrase_repository: PhraseRepository
    clock: Clock

    def execute(self, query: GetUserProgressQuery) -> UserProgressSnapshot:
        return self.phrase_repository.get_progress_snapshot(
            user_id=query.user_id,
            now=self.clock.now(),
        )


@dataclass(slots=True)
class GetSettingsUseCase:
    """Return user settings, creating defaults on the fly."""

    settings_repository: SettingsRepository

    def execute(self, query: GetSettingsQuery) -> UserSettingsSnapshot:
        settings = self.settings_repository.get(query.user_id) or (
            default_settings(query.user_id)
        )
        return map_settings_snapshot(settings)


@dataclass(slots=True)
class UpdateSettingsUseCase:
    """Persist updated user settings."""

    settings_repository: SettingsRepository

    def execute(self, command: UpdateSettingsCommand) -> UserSettingsSnapshot:
        source_lang = self._normalize_language_code(
            command.default_source_lang
        )
        target_lang = self._normalize_language_code(
            command.default_target_lang
        )
        self._validate(
            source_lang=source_lang,
            target_lang=target_lang,
            timezone=command.timezone,
        )
        current = self.settings_repository.get(command.user_id) or (
            default_settings(command.user_id)
        )
        settings = UserSettings(
            user_id=command.user_id,
            default_source_lang=source_lang,
            default_target_lang=target_lang,
            default_translation_direction=(
                command.default_translation_direction
            ),
            timezone=command.timezone,
            notification_time_local=command.notification_time_local,
            notifications_enabled=command.notifications_enabled,
            last_notification_local_date=current.last_notification_local_date,
        )
        stored = self.settings_repository.save(settings)
        return map_settings_snapshot(stored)

    def _validate(
        self,
        *,
        source_lang: str,
        target_lang: str,
        timezone: str,
    ) -> None:
        if source_lang == target_lang:
            raise InvalidSettingsError(
                "Source and target languages must differ."
            )
        if not LANGUAGE_CODE_PATTERN.fullmatch(source_lang):
            raise InvalidSettingsError("Source language code is invalid.")
        if not LANGUAGE_CODE_PATTERN.fullmatch(target_lang):
            raise InvalidSettingsError("Target language code is invalid.")
        try:
            ZoneInfo(timezone)
        except ZoneInfoNotFoundError as error:
            raise InvalidSettingsError(
                "Timezone must be a valid IANA timezone."
            ) from error

    @staticmethod
    def _normalize_language_code(language_code: str) -> str:
        normalized = normalize_language_code(language_code)
        if normalized is None:
            raise InvalidSettingsError("Language code is invalid.")
        return normalized


@dataclass(slots=True)
class StartQuizSessionUseCase:
    """Start or resume a persistent Telegram quiz session."""

    phrase_repository: PhraseRepository
    quiz_session_repository: QuizSessionRepository
    clock: Clock

    def execute(
        self,
        user_id: int,
        *,
        activate: bool = False,
        message_id: int | None = None,
    ) -> QuizSessionStartResult | None:
        existing = self.quiz_session_repository.get(user_id)
        if existing is not None:
            session = self._resume(existing)
            if session is not None:
                session = self._activate_session(
                    session=session,
                    activate=activate,
                    message_id=message_id,
                )
                return self._build_start_result(session)
            self.quiz_session_repository.delete(user_id)
        due_reviews = mix_due_reviews(
            list_due_reviews(
                phrase_repository=self.phrase_repository,
                user_id=user_id,
                now=self.clock.now(),
            )
        )
        if not due_reviews:
            return None
        session_reviews = due_reviews[:QUIZ_SESSION_LIMIT]
        first_review = session_reviews[0]
        session = TelegramQuizSession(
            user_id=user_id,
            card_id=first_review.card_id,
            direction=first_review.direction,
            started_at=self.clock.now(),
            pending_reviews=tuple(
                QuizReviewPointer(
                    card_id=item.card_id,
                    direction=item.direction,
                )
                for item in session_reviews[1:]
            ),
            total_prompts=len(session_reviews),
            due_reviews_total=len(due_reviews),
            awaiting_start=not activate,
            message_id=message_id,
        )
        session = self.quiz_session_repository.save(session)
        return self._build_start_result(session)

    def _build_start_result(
        self, session: TelegramQuizSession
    ) -> QuizSessionStartResult:
        return QuizSessionStartResult(
            prompt=self._build_prompt(session),
            due_reviews_total=session.due_reviews_total,
            session_prompts_total=session.total_prompts,
            awaiting_start=session.awaiting_start,
        )

    def _resume(
        self, session: TelegramQuizSession
    ) -> TelegramQuizSession | None:
        try:
            card = load_user_card(
                self.phrase_repository, session.card_id, session.user_id
            )
        except CardNotFoundError:
            return None
        if card.learning_status is not LearningStatus.ACTIVE:
            return None
        track = card.track_for(session.direction)
        if not track.is_due(self.clock.now()):
            return None
        return session

    def _activate_session(
        self,
        *,
        session: TelegramQuizSession,
        activate: bool,
        message_id: int | None,
    ) -> TelegramQuizSession:
        if not activate and message_id is None:
            return session
        updated = session
        if activate and session.awaiting_start:
            updated = replace(updated, awaiting_start=False)
        if message_id is not None and updated.message_id != message_id:
            updated = replace(updated, message_id=message_id)
        if updated == session:
            return session
        return self.quiz_session_repository.save(updated)

    def _build_prompt(
        self, session: TelegramQuizSession
    ) -> QuizSessionPrompt:
        card = load_user_card(
            phrase_repository=self.phrase_repository,
            card_id=session.card_id,
            user_id=session.user_id,
        )
        return build_quiz_prompt(
            card=card,
            direction=session.direction,
            session_position=session.answered_prompts + 1,
            total_prompts=session.total_prompts,
        )


@dataclass(slots=True)
class SkipQuizSessionUseCase:
    """Skip the current card and advance the Telegram quiz session."""

    phrase_repository: PhraseRepository
    quiz_session_repository: QuizSessionRepository
    clock: Clock

    def execute(self, user_id: int) -> SkipQuizResult | None:
        session = self.quiz_session_repository.get(user_id)
        if session is None:
            return None
        next_session = self._advance(session)
        if next_session is None:
            self.quiz_session_repository.delete(user_id)
            return SkipQuizResult(
                next_prompt=None,
                session_summary=self._build_summary(session),
            )
        stored_session = self.quiz_session_repository.save(next_session)
        return SkipQuizResult(
            next_prompt=self._build_prompt(stored_session),
            session_summary=None,
        )

    def _advance(
        self, session: TelegramQuizSession
    ) -> TelegramQuizSession | None:
        if not session.pending_reviews:
            return None
        next_item = session.pending_reviews[0]
        return replace(
            session,
            card_id=next_item.card_id,
            direction=next_item.direction,
            pending_reviews=session.pending_reviews[1:],
            awaiting_start=False,
        )

    def _build_prompt(
        self, session: TelegramQuizSession
    ) -> QuizSessionPrompt:
        card = load_user_card(
            phrase_repository=self.phrase_repository,
            card_id=session.card_id,
            user_id=session.user_id,
        )
        return build_quiz_prompt(
            card=card,
            direction=session.direction,
            session_position=session.answered_prompts + 1,
            total_prompts=session.total_prompts,
        )

    def _build_summary(
        self, session: TelegramQuizSession
    ) -> QuizSessionSummary:
        remaining_due_reviews = len(
            list_due_reviews(
                phrase_repository=self.phrase_repository,
                user_id=session.user_id,
                now=self.clock.now(),
            )
        )
        return build_quiz_summary(
            total_prompts=session.total_prompts,
            answered_prompts=session.answered_prompts,
            correct_prompts=session.correct_prompts,
            incorrect_prompts=session.incorrect_prompts,
            remaining_due_reviews=remaining_due_reviews,
        )


@dataclass(slots=True)
class EndQuizSessionUseCase:
    """Exit the active Telegram quiz session immediately."""

    quiz_session_repository: QuizSessionRepository

    def execute(self, user_id: int) -> bool:
        session = self.quiz_session_repository.get(user_id)
        if session is None:
            return False
        self.quiz_session_repository.delete(user_id)
        return True


@dataclass(slots=True)
class SubmitActiveQuizAnswerUseCase:
    """Submit an answer for the current Telegram quiz session."""

    quiz_session_repository: QuizSessionRepository
    phrase_repository: PhraseRepository
    submit_review_answer_use_case: SubmitReviewAnswerUseCase
    clock: Clock

    def execute(
        self, user_id: int, answer_text: str
    ) -> ActiveQuizAnswerResult:
        session = self.quiz_session_repository.get(user_id)
        if session is None:
            raise QuizSessionNotFoundError("No active quiz session was found.")
        if session.awaiting_start:
            raise QuizSessionNotFoundError("Start the quiz before answering.")
        review_result = self.submit_review_answer_use_case.execute(
            SubmitReviewAnswerCommand(
                user_id=user_id,
                card_id=session.card_id,
                direction=session.direction,
                answer_text=answer_text,
            )
        )
        next_session = self._advance(
            session=session,
            was_correct=review_result.outcome is ReviewOutcome.CORRECT,
        )
        if next_session is None:
            self.quiz_session_repository.delete(user_id)
            return ActiveQuizAnswerResult(
                review_result=review_result,
                next_prompt=None,
                session_summary=self._build_summary(
                    session=session,
                    was_correct=review_result.outcome
                    is ReviewOutcome.CORRECT,
                ),
            )
        stored_session = self.quiz_session_repository.save(next_session)
        return ActiveQuizAnswerResult(
            review_result=review_result,
            next_prompt=self._build_prompt(stored_session),
            session_summary=None,
        )

    def _advance(
        self,
        *,
        session: TelegramQuizSession,
        was_correct: bool,
    ) -> TelegramQuizSession | None:
        if not session.pending_reviews:
            return None
        next_item = session.pending_reviews[0]
        return replace(
            session,
            card_id=next_item.card_id,
            direction=next_item.direction,
            pending_reviews=session.pending_reviews[1:],
            answered_prompts=session.answered_prompts + 1,
            correct_prompts=(
                session.correct_prompts + (1 if was_correct else 0)
            ),
            incorrect_prompts=(
                session.incorrect_prompts + (0 if was_correct else 1)
            ),
            awaiting_start=False,
        )

    def _build_prompt(
        self, session: TelegramQuizSession
    ) -> QuizSessionPrompt:
        card = load_user_card(
            phrase_repository=self.phrase_repository,
            card_id=session.card_id,
            user_id=session.user_id,
        )
        return build_quiz_prompt(
            card=card,
            direction=session.direction,
            session_position=session.answered_prompts + 1,
            total_prompts=session.total_prompts,
        )

    def _build_summary(
        self,
        *,
        session: TelegramQuizSession,
        was_correct: bool,
    ) -> QuizSessionSummary:
        remaining_due_reviews = len(
            list_due_reviews(
                phrase_repository=self.phrase_repository,
                user_id=session.user_id,
                now=self.clock.now(),
            )
        )
        return build_quiz_summary(
            total_prompts=session.total_prompts,
            answered_prompts=session.answered_prompts + 1,
            correct_prompts=(
                session.correct_prompts + (1 if was_correct else 0)
            ),
            incorrect_prompts=(
                session.incorrect_prompts + (0 if was_correct else 1)
            ),
            remaining_due_reviews=remaining_due_reviews,
        )
