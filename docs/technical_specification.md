# Technical Specification: Spaced Repetition Telegram Bot

## 1. Overview

SpacedRepetitionBot is a Telegram-first service for saving translated phrases
and reviewing them through a fixed spaced repetition schedule.

Specification review date: `2026-03-29`.

The current delivery stage covers the main product functionality, persistent
storage, Telegram reminders, and automated quality checks. Migration tooling
and broader product expansion are deferred to a later stage.

## 2. Product Goals

### 2.1 Primary Goal

Reduce the path from "I found an unfamiliar phrase" to "I translated it, saved
it, and reviewed it on time" to a single Telegram workflow.

### 2.2 Product Outcomes

The product must:

- translate phrases inside Telegram
- persist saved phrases and settings across restarts
- schedule phrase reviews automatically
- support both directions within one active language pair
- remind users when reviews are due
- let users pause and restore cards without deleting history

## 3. Key Product Decisions from the Q&A

- Only one active language pair is supported per user.
- The spaced repetition schedule is fixed at `2 / 3 / 5 / 7`.
- A phrase is fully learned only after both review directions are completed.
- The quiz format is manual text input only.
- Answer validation is tolerant to case, repeated spaces, and common hyphen
  differences.
- An incorrect answer fully resets the current review track.
- Skipping a quiz leaves the card due for later review.
- Notification scheduling is time-based, not frequency-based, in this phase.
- Phrase edit and delete flows are out of scope for the current MVP.
- History storage has no hard cap in this phase, while API responses return
  bounded slices.
- Persistent state is keyed by Telegram user id and shared across user devices
  and sessions.
- SQLite is sufficient for the current implementation stage.

## 4. Competitive and Technical Benchmarks

### 4.1 Current Best-in-Class References

1. `Anki + FSRS`
   Strong reference point for review quality and long-term retention.

2. `Quizlet / Duolingo`
   Strong examples of accessible learning UX, but weaker for user-owned phrase
   capture.

3. `Telegram-first learning bots`
   The closest product pattern for low-friction daily usage.

### 4.2 Product Positioning

This service prioritizes phrase capture and review inside an existing messaging
interface rather than a content-heavy course platform.

### 4.3 Recommended Stack

- `Python 3.12+`
- `aiogram 3.x`
- `FastAPI`
- `Pydantic v2`
- `SQLAlchemy 2.x`
- `SQLite` for the current MVP

### 4.4 Research Sources

- aiogram docs: https://docs.aiogram.dev/en/latest/
- FastAPI OpenAPI reference: https://fastapi.tiangolo.com/reference/openapi/
- Pydantic models: https://docs.pydantic.dev/latest/concepts/models/
- SQLAlchemy declarative mapping: https://docs.sqlalchemy.org/20/orm/declarative_mapping.html
- FSRS algorithm reference: https://github.com/open-spaced-repetition/fsrs4anki/wiki/The-Algorithm

## 5. Implemented Scope

### 5.1 Included

- phrase translation between languages `A` and `B`
- one active language pair per user
- one default translation direction per user
- translation history
- persistent phrase cards
- opt-out from learning while keeping history
- restore from `not_learning`
- bidirectional quizzes
- manual answer checking
- reminder delivery inside the Telegram bot process
- user settings for pair, direction, timezone, notification time, and
  notification enable state
- HTTP API with OpenAPI documentation
- Telegram chat-first flow with buttons, guided settings input, and reviews
- automated syntax, lint, complexity, and test checks

### 5.2 Deferred

- notification frequency as a separate setting
- multiple quiz formats
- semantic answer matching
- phrase editing and deletion
- multiple active language pairs per user
- analytics beyond current learning state
- migration tooling

## 6. Functional Requirements

### 6.1 Translation

1. The user sends a phrase as text.
2. The system uses the stored active language pair.
3. The system applies the current translation direction:
   - `forward` means `A -> B`
   - `reverse` means `B -> A`
4. The translation result is returned to the user.
5. If learning is enabled, a card is persisted with review tracks for both
   directions.
6. The Telegram response may warn the user when the translated text matches the
   source text or the detected source language does not match the active pair.
7. The Telegram translation card offers actions for reverse direction, quiz,
   settings, and learning control.

### 6.2 History

1. Every translation is stored per user.
2. The user can request recent translation history.
3. History must show:
   - card id or short id prefix
   - source phrase
   - translated phrase
   - language pair
   - creation date
   - learning status
4. The API returns bounded history slices per request.
5. Telegram history uses short card ids for quick `not_learning` and `restore`
   commands.

### 6.3 Learning Control

1. The user can mark a card as `not_learning`.
2. The card is removed from the review queue.
3. The card remains in history.
4. The user can restore the card later.

### 6.4 Review Scheduling

1. The review schedule is fixed at `2 / 3 / 5 / 7`.
2. Each card creates two review tracks:
   - `forward`
   - `reverse`
3. A correct answer advances the track.
4. An incorrect answer resets the track to the first interval.
5. A track is completed after the final successful step.
6. A card is learned only when both tracks are completed.

### 6.5 Quiz Flow

1. The service fetches the due reviews for a user.
2. The bot starts or resumes one active quiz session per user.
3. Each quiz session is capped to a short prompt batch in the Telegram UX.
4. The bot presents a session intro before the first prompt.
5. The prompt shows the phrase in the language required by the selected review
   direction.
6. The user answers manually with text.
7. The answer checker normalizes:
   - surrounding whitespace
   - letter case
   - repeated spaces
   - common hyphen and dash variants
8. The result updates review progress.
9. The next due prompt is offered automatically when available.
10. Skipping a card keeps it due and advances to the next prompt in the active
    session when possible.
11. The user can end the session explicitly without resetting due cards.
12. At session completion, the bot shows a summary with answered, correct,
    incorrect, and remaining due counts.

### 6.6 Notifications

1. Notification delivery runs inside the Telegram bot process.
2. Reminder scheduling respects:
   - stored timezone
   - stored local notification time
   - notification enabled state
3. A user receives a reminder only when due reviews exist.
4. A user receives at most one reminder per local day.
5. Reminder messages provide a direct Telegram action to start a quiz session.

### 6.7 Settings

Users can change:

- default source language
- default target language
- default translation direction
- timezone
- preferred notification time
- notification enabled state

The Telegram settings flow supports:

- inline button toggles for direction and notifications
- guided text input for pair, timezone, and reminder time
- `/cancel` for exiting an active guided input flow

## 7. Architecture

### 7.1 Architectural Style

The project uses `Clean Architecture` with four layers:

- `domain`
- `application`
- `infrastructure`
- `presentation`

### 7.2 Layer Responsibilities

#### Domain

- entities: `PhraseCard`, `ReviewTrack`, `UserSettings`, `TelegramQuizSession`
- enums and core business rules
- fixed review policy and answer normalization policy

#### Application

- use cases
- commands, queries, and result DTOs
- repository and provider ports
- orchestration of translation, review, settings, and quiz session flows

#### Infrastructure

- SQLAlchemy repositories
- SQLite schema
- translation adapter
- configuration and clock adapters
- Telegram reminder service

#### Presentation

- FastAPI routes and schemas
- aiogram handlers and command UX

### 7.3 Applied Patterns

- `Ports and Adapters`
- `Repository`
- `Strategy`
- `Dependency Injection`
- `DTO`
- `Composition Root`

## 8. Domain Model

### 8.1 PhraseCard

- `id`
- `user_id`
- `source_text`
- `target_text`
- `source_lang`
- `target_lang`
- `created_at`
- `learning_status`
- `review_tracks`
- `archived_reason`

### 8.2 ReviewTrack

- `direction`
- `step_index`
- `next_review_at`
- `review_count`
- `last_outcome`
- `completed_at`

### 8.3 UserSettings

- `user_id`
- `default_source_lang`
- `default_target_lang`
- `default_translation_direction`
- `timezone`
- `notification_time_local`
- `notifications_enabled`
- `last_notification_local_date`

### 8.4 TelegramQuizSession

- `user_id`
- `card_id`
- `direction`
- `started_at`

## 9. Core Use Cases

1. `TranslatePhrase`
2. `GetHistory`
3. `ToggleLearning`
4. `GetDueReviews`
5. `StartQuizSession`
6. `SkipQuizSession`
7. `SubmitReviewAnswer`
8. `SubmitActiveQuizAnswer`
9. `GetProgress`
10. `GetSettings`
11. `UpdateSettings`

## 10. API Requirements

### 10.1 Implemented Endpoints

- `GET /api/v1/health`
- `POST /api/v1/translations`
- `GET /api/v1/history`
- `PATCH /api/v1/cards/{card_id}/learning`
- `GET /api/v1/reviews/due`
- `POST /api/v1/reviews/{card_id}/answer`
- `GET /api/v1/progress`
- `GET /api/v1/settings`
- `PUT /api/v1/settings`

### 10.2 API Rules

- every public endpoint must be described by OpenAPI
- translation requests use the stored active language pair
- translation requests may override only the direction within that pair
- settings updates must validate timezone and prevent identical source and
  target languages
- error responses must be standardized

## 11. Persistence

### 11.1 Current Storage

- `SQLite`
- schema creation through SQLAlchemy metadata initialization

### 11.2 Logical Tables

#### `cards`

- `id`
- `user_id`
- `source_text`
- `target_text`
- `source_lang`
- `target_lang`
- `learning_status`
- `created_at`
- `archived_reason`

#### `review_tracks`

- `id`
- `card_id`
- `direction`
- `step_index`
- `next_review_at`
- `review_count`
- `last_outcome`
- `completed_at`

#### `user_settings`

- `user_id`
- `default_source_lang`
- `default_target_lang`
- `default_translation_direction`
- `timezone`
- `notification_time_local`
- `notifications_enabled`
- `last_notification_local_date`

#### `telegram_quiz_sessions`

- `user_id`
- `card_id`
- `direction`
- `started_at`
- `pending_reviews_json`
- `total_prompts`
- `due_reviews_total`
- `answered_prompts`
- `correct_prompts`
- `incorrect_prompts`
- `awaiting_start`
- `message_id`

## 12. Integrations

### 12.1 Telegram

- bot token from environment variables
- long polling entrypoint
- chat-first interaction style with inline buttons
- plain text translation outside an active quiz session
- plain text answer handling during an active quiz session
- guided settings input for pair, timezone, and reminder time
- quiz session intro, progress feedback, and session summary messages
- shared state across devices by Telegram user id

Supported commands:

- `/start`
- `/history`
- `/progress`
- `/settings`
- `/pair`
- `/direction`
- `/notifytime`
- `/timezone`
- `/notifications`
- `/quiz`
- `/skip`
- `/notlearning`
- `/restore`
- `/cancel`

### 12.2 Translation Provider

Provider interface:

- `translate(text, source_lang, target_lang) -> TranslationGatewayResult`

Implemented adapters:

- `MockTranslationProvider`
- `YandexTranslationProvider`

## 13. Review Logic

### 13.1 MVP Rule

The intervals `2 / 3 / 5 / 7` are treated as relative steps between successful
answers.

### 13.2 Upgrade Path

The architecture keeps review policy and translation provider logic behind
replaceable interfaces so the implementation can evolve without rewriting
presentation or domain entities.

## 14. Acceptance Criteria for the Current Stage

The current core-functionality stage is acceptable when:

- translation, history, settings, quiz, and reminder flows work end to end
- cards, settings, and active quiz sessions persist across restarts
- the Telegram bot and HTTP API operate on the same stored data
- the implemented commands and endpoints match the documented behavior
- syntax passes `python3 -m compileall`
- lint, complexity, and test checks pass in the supported development setup
