# SpacedRepetitionBot

SpacedRepetitionBot is a Telegram-first vocabulary learning service that joins
translation, spaced repetition, reminders, and progress tracking in one flow.

This repository currently focuses on the core MVP functionality:

- persistent SQLite storage
- Telegram translation cards with action buttons
- bidirectional quiz sessions
- scheduled reminder delivery
- user settings and learning controls
- automated tests and quality checks

## Repository Layout

- `docs/technical_specification.md` - product and engineering specification
- `src/spaced_repetition_bot` - application source code
- `.env.example` - environment template

## Stack

- `Python 3.12+`
- `aiogram 3.x`
- `FastAPI`
- `Pydantic v2`
- `SQLAlchemy 2.x`
- `SQLite`

## Quick Start

### 1. Requirements

Install:

- `Python 3.12+`
- `pip`
- `venv`

Check the interpreter version:

```bash
python3 --version
```

### 2. Clone the Repository

```bash
git clone <repo-url>
cd SpacedRepetitionBot
```

### 3. Create a Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

For Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 4. Install Dependencies

```bash
python3 -m pip install --upgrade pip
python3 -m pip install -e .
```

### 5. Configure the Environment

Create a local `.env` file from the template:

```bash
cp .env.example .env
```

Default example:

```env
SRB_APP_NAME=Spaced Repetition Bot
SRB_APP_VERSION=0.1.0
SRB_API_PREFIX=/api/v1
SRB_DEBUG=false
SRB_DATABASE_URL=sqlite:///./spaced_repetition_bot.db
SRB_TELEGRAM_BOT_TOKEN=change-me
SRB_REMINDER_POLL_INTERVAL_SECONDS=60
SRB_REVIEW_INTERVALS=2,3,5,7
SRB_REVIEW_INTERVAL_UNIT=days
SRB_TRANSLATION_PROVIDER=mock
SRB_YANDEX_TRANSLATE_API_KEY=
SRB_YANDEX_FOLDER_ID=
SRB_YANDEX_TRANSLATE_URL=https://translate.api.cloud.yandex.net/translate/v2/translate
SRB_TRANSLATION_TIMEOUT_SECONDS=10
```

Notes:

- `sqlite:///./spaced_repetition_bot.db` is the default persistent local database
- `SRB_TELEGRAM_BOT_TOKEN` must be replaced before starting the Telegram bot
- `SRB_REVIEW_INTERVALS` defaults to `2,3,5,7`
- `SRB_REVIEW_INTERVAL_UNIT` defaults to `days` and can be switched to
  `minutes` for fast local reminder testing
- `SRB_TRANSLATION_PROVIDER=mock` keeps the deterministic local translator
- switch `SRB_TRANSLATION_PROVIDER` to `yandex` only after setting
  `SRB_YANDEX_TRANSLATE_API_KEY` and `SRB_YANDEX_FOLDER_ID`

### 6. Start the API

```bash
uvicorn spaced_repetition_bot.main:app --reload
```

Available endpoints:

- OpenAPI UI: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/api/v1/health`

Verify that the API is running:

```bash
curl http://127.0.0.1:8000/api/v1/health
```

Expected response:

```json
{"status":"ok","version":"0.1.0"}
```

### 7. Send a First API Request

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/translations" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 1,
    "text": "good luck",
    "direction": "forward",
    "learn": true
  }'
```

The translation request uses the user’s stored active language pair. The
optional `direction` field switches between `forward` and `reverse` inside that
pair. By default the application uses the built-in deterministic translation
adapter. Set `SRB_TRANSLATION_PROVIDER=yandex` to use Yandex Cloud Translate.

### 7.1 Enable Yandex Translate

Update `.env`:

```env
SRB_TRANSLATION_PROVIDER=yandex
SRB_YANDEX_TRANSLATE_API_KEY=<your-api-key>
SRB_YANDEX_FOLDER_ID=<your-folder-id>
SRB_YANDEX_TRANSLATE_URL=https://translate.api.cloud.yandex.net/translate/v2/translate
SRB_TRANSLATION_TIMEOUT_SECONDS=10
```

When `SRB_TRANSLATION_PROVIDER=yandex`, the application fails on startup if the
API key or folder id is missing.

### 8. Start the Telegram Bot

Set a real token in `.env`:

```env
SRB_TELEGRAM_BOT_TOKEN=<your-token>
```

Start long polling:

```bash
python3 -m spaced_repetition_bot.run_telegram_bot
```

The bot process also runs the reminder scheduler. Run the API and Telegram bot
as separate processes if you want both interfaces available at the same time.
Persistent bot state is keyed by Telegram user id, so saved cards, settings,
and quiz progress are shared across user devices.

In Telegram, the default happy path is chat-first:

- plain text creates a translation card
- suspicious translations stay unsaved until the user confirms `Keep anyway`
- inline buttons open settings, pause or restore cards, and launch quizzes
- `/quiz` opens a short review session with `Start quiz`, `Skip card`, and
  `End session`
- reminder messages include a direct `Start quiz` button

### 8.1 Fast Reminder Testing

For local reminder tests, switch the review schedule from days to minutes:

```env
SRB_REVIEW_INTERVALS=2,3,5,7
SRB_REVIEW_INTERVAL_UNIT=minutes
SRB_REMINDER_POLL_INTERVAL_SECONDS=5
```

This keeps the default production behavior unchanged while letting you verify
the reminder flow without waiting for multiple days.

## Telegram Commands

- `/start`
- `/history`
- `/progress`
- `/settings`
- `/pair <source_lang> <target_lang>`
- `/direction <forward|reverse>`
- `/notifytime <HH:MM>`
- `/notifyevery <days>`
- `/timezone <IANA timezone>`
- `/notifications <on|off>`
- `/quiz`
- `/skip`
- `/notlearning <card_id|short_id>`
- `/restore <card_id|short_id>`
- `/cancel`

Plain text behavior:

- if there is an active quiz session, the next plain text message is treated as the answer
- otherwise, plain text is translated and optionally saved as a learning card

## Core Product Rules

- one active language pair per user
- one default translation direction per user
- fixed spaced repetition schedule: `2 / 3 / 5 / 7`
- two review tracks per card: `forward` and `reverse`
- a card is learned only after both tracks are completed
- quiz answers use manual text input only
- answer matching ignores case, extra spaces, and common hyphen differences
- an incorrect answer resets the track to the beginning
- skipping a quiz leaves the card due
- cards marked as `not_learning` stay in history and can be restored
- exact duplicate cards are reused instead of being created again
- quiz sessions spread the same card directions apart when possible
- warning previews are written to history immediately and updated in place if kept
- `/history` shows short card ids for quick pause and restore commands

## HTTP API

Implemented endpoints:

- `GET /api/v1/health`
- `POST /api/v1/translations`
- `GET /api/v1/history`
- `PATCH /api/v1/cards/{card_id}/learning`
- `GET /api/v1/reviews/due`
- `POST /api/v1/reviews/{card_id}/answer`
- `GET /api/v1/progress`
- `GET /api/v1/settings`
- `PUT /api/v1/settings`

## Current Deferred Items

- multiple quiz formats
- phrase edit and delete flows
- multiple active language pairs per user
- advanced analytics
- dedicated migration tooling

## Quality Checks

```bash
python3 -m compileall src tests
.venv/bin/python -m flake8 src tests
.venv/bin/python scripts/check_complexity.py src/ --max 9
.venv/bin/python -m pytest -q
```

## Troubleshooting

### `spaced_repetition_bot` cannot be imported

The project is not installed in the current environment:

```bash
python3 -m pip install -e .
```

### The Telegram bot does not respond

Check the following:

- the virtual environment is active
- `SRB_TELEGRAM_BOT_TOKEN` is set in `.env`
- the token is not still `change-me`
- the bot is running in a separate process from `uvicorn`

### The API works but reminders do not arrive

Check the following:

- the Telegram bot process is running
- notifications are enabled with `/notifications on`
- the user timezone and notification time are configured correctly
- the user already has saved cards and due reviews

### The app does not start with `SRB_TRANSLATION_PROVIDER=yandex`

Check the following:

- `SRB_YANDEX_TRANSLATE_API_KEY` is set
- `SRB_YANDEX_FOLDER_ID` is set
- `SRB_YANDEX_TRANSLATE_URL` points to the expected Yandex endpoint

### `uvicorn` is not found

Install the project in the current environment:

```bash
python3 -m pip install -e .
```

## Useful Files

- `docs/technical_specification.md` - full specification
- `.env.example` - environment template
- `src/spaced_repetition_bot/main.py` - FastAPI entrypoint
- `src/spaced_repetition_bot/run_telegram_bot.py` - Telegram polling entrypoint
