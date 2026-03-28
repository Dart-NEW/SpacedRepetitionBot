# Technical Specification: Spaced Repetition Telegram Bot

## 1. Overview

The service combines translation and spaced repetition in a single Telegram bot.
Users translate phrases directly in chat, keep a searchable history, review due
cards on schedule, and track progress without switching between multiple tools.

Specification review date: `2026-03-28`.

## 2. Product Goals

### 2.1 Primary Goal

Reduce the path from "I found an unfamiliar phrase" to "I added it to my study
flow and reviewed it on time" to a single Telegram conversation.

### 2.2 Product Outcomes

The product should:

- translate phrases in chat
- turn translations into review cards
- schedule reviews automatically
- support both translation directions
- keep reminders useful and non-intrusive

## 3. Competitive and Technical Benchmarks

### 3.1 Current Best-in-Class References

1. `Anki + FSRS`
   The strongest reference point for modern spaced repetition systems. FSRS is
   widely used as a practical adaptive review scheduler.

2. `Quizlet / Duolingo`
   Strong in usability and packaged learning content, but weaker for the
   user-owned phrase capture workflow this product targets.

3. `Telegram-first learning bots`
   Strongest fit for low-friction capture and review because the interaction
   happens in a tool users already open multiple times per day.

### 3.2 Product Decision

- The MVP must follow the fixed assignment schedule `2 / 3 / 5 / 7`.
- The architecture must allow a later switch to `FSRS` without rewriting core
  use cases.
- Translation must be hidden behind a `TranslationProvider` port so providers
  can be swapped cleanly.

### 3.3 Recommended Stack

- `Python 3.12+`
- `aiogram 3.x`
- `FastAPI`
- `Pydantic v2`
- `SQLAlchemy 2.x`
- `Alembic`
- `httpx`
- `SQLite` for MVP, `PostgreSQL` for production
- `pytest`, `pytest-cov`, `flake8`, `radon`, `bandit`, `locust`, `safety`

### 3.4 Rationale

- `aiogram 3.x` provides an async-first, router-based Telegram integration.
- `FastAPI` produces OpenAPI documentation automatically and works well with a
  typed application layer.
- `Pydantic v2` is a strong fit for DTO validation and JSON schema generation.
- `SQLAlchemy 2.x` fits clean architecture and supports both MVP and production
  persistence strategies.
- `SQLite` keeps the MVP simple while preserving a clean path to
  `PostgreSQL`.

### 3.5 Research Sources

- aiogram docs: https://docs.aiogram.dev/en/latest/
- FastAPI OpenAPI reference: https://fastapi.tiangolo.com/reference/openapi/
- Pydantic models: https://docs.pydantic.dev/latest/concepts/models/
- SQLAlchemy declarative mapping: https://docs.sqlalchemy.org/20/orm/declarative_mapping.html
- Google Cloud Translation docs: https://docs.cloud.google.com/translate/docs/samples/translate-translate-text
- FSRS algorithm reference: https://github.com/open-spaced-repetition/fsrs4anki/wiki/The-Algorithm

## 4. MVP Scope

### 4.1 Included

- phrase translation between languages `A` and `B`
- translation history
- card creation during translation
- opt-out from learning while keeping history
- bidirectional quizzes
- manual text answers
- progress reset on incorrect answers
- progress summary
- language and notification settings
- HTTP API with OpenAPI
- Telegram integration as a separate adapter

### 4.2 Excluded

- production-grade FSRS scheduling
- voice messages
- OCR
- multimedia cards
- shared dictionaries
- semantic answer matching
- retention analytics

## 5. Functional Requirements

### 5.1 Translation

1. The user sends a phrase as text.
2. The service determines the direction:
   - default `A -> B`
   - optional override `B -> A`
3. The bot returns the translation.
4. If learning is enabled, the service creates a card and schedules reviews.

### 5.2 History

1. The service stores every translation for a user.
2. The user can request recent translations.
3. History must show:
   - source phrase
   - translated phrase
   - language pair
   - creation date
   - learning status

### 5.3 Excluding a Card from Learning

1. The user can mark a card as `not_learning`.
2. The card is removed from the review queue.
3. The card remains in translation history.

### 5.4 Review Scheduling

1. The MVP uses the fixed schedule `2 / 3 / 5 / 7`.
2. Each card creates two independent review tracks:
   - `forward`: `A -> B`
   - `reverse`: `B -> A`
3. A correct answer advances the track.
4. An incorrect answer resets the track to the first interval.
5. A track is marked complete after all steps are passed.
6. A card is fully learned only when both tracks are complete.

### 5.5 Quiz Flow

1. The service fetches all due reviews.
2. The user sees the phrase in one language.
3. The user answers manually with text.
4. The answer checker normalizes:
   - leading and trailing whitespace
   - case
   - repeated spaces
5. The result updates review progress.

### 5.6 Settings

Users can change:

- default source language
- default target language
- time zone
- preferred notification time
- notification enabled state

## 6. Non-Functional Requirements

The project targets the following quality thresholds:

- cyclomatic complexity `< 10` per function
- maintainability index `> 70%`
- `flake8` with zero style errors
- OpenAPI coverage for all public API routes
- line coverage `>= 80%`
- passing `pytest`
- no high-severity `bandit` findings
- acceptable `safety` results
- `P95 < 300ms` for local MVP API requests, excluding external translation time

## 7. Architecture

### 7.1 Architectural Style

The project uses `Clean Architecture` with four layers:

- `domain`
- `application`
- `infrastructure`
- `presentation`

### 7.2 Layer Responsibilities

#### Domain

- entities: `PhraseCard`, `ReviewTrack`, `UserSettings`
- enums and value-like data structures
- review and answer policies
- business rules without framework dependencies

#### Application

- use cases
- commands, queries, and result DTOs
- repository and provider ports
- orchestration of business scenarios

#### Infrastructure

- repository implementations
- translation provider implementations
- configuration loading
- clock and runtime adapters
- persistence adapters for later SQL integration

#### Presentation

- FastAPI routes
- request and response schemas
- Telegram handlers and routers

### 7.3 Patterns

- `Ports and Adapters`
- `Repository`
- `Strategy`
- `Dependency Injection`
- `DTO`
- `Entity`
- `Composition over inheritance`

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
- `timezone`
- `notification_time_local`
- `notifications_enabled`

## 9. Core Use Cases

1. `TranslatePhrase`
2. `GetHistory`
3. `ToggleLearning`
4. `GetDueReviews`
5. `SubmitReviewAnswer`
6. `GetProgress`
7. `UpdateSettings`
8. `GetSettings`

## 10. API Requirements

### 10.1 Minimum Endpoints

- `GET /api/v1/health`
- `POST /api/v1/translations`
- `GET /api/v1/history`
- `PATCH /api/v1/cards/{card_id}/learning`
- `GET /api/v1/reviews/due`
- `POST /api/v1/reviews/{card_id}/answer`
- `GET /api/v1/progress`
- `GET /api/v1/settings`
- `PUT /api/v1/settings`

### 10.2 Documentation Rules

- every public endpoint must be described by OpenAPI
- path, query, and body parameters must have descriptions
- every request must have at least one documented response example
- error responses must be standardized

## 11. Persistence

### 11.1 MVP Storage

- `SQLite`
- migrations with `Alembic`

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
- `timezone`
- `notification_time_local`
- `notifications_enabled`

## 12. Integrations

### 12.1 Telegram

- bot token via environment variables
- webhook or long polling
- commands `/start`, `/history`, `/progress`, `/settings`
- plain text treated as translation input

### 12.2 Translation Provider

Provider interface:

- `translate(text, source_lang, target_lang) -> TranslationResult`

Adapters:

- `MockTranslationProvider` for local development
- `GoogleTranslateProvider` or `DeepLProvider` for production

## 13. Review Logic

### 13.1 MVP Rule

The intervals `2 / 3 / 5 / 7` are treated as relative steps between successful
answers. This keeps the reset behavior simple and predictable.

### 13.2 Upgrade Path

The architecture must support both:

- `FixedIntervalPolicy` for the assignment-aligned MVP
- `FsrsPolicy` for a later adaptive scheduler

The switch should happen in the composition root rather than inside the use
cases.

## 14. Security and Observability

- secrets must be loaded from environment variables
- structured logging
- basic rate limiting at the API and bot edge
- idempotent handling for repeated updates
- health-check endpoint
- trace-friendly request identifiers in logs

## 15. Acceptance Criteria

Changes and feature increments are acceptable when:

- the use case works end to end
- positive and negative tests exist
- the endpoint is documented
- syntax passes `python3 -m compileall`
- quality gates remain green
