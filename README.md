# SpacedRepetitionBot

SpacedRepetitionBot is a Telegram-first vocabulary learning service that combines
translation, review scheduling, and progress tracking in a single workflow.

## Repository Layout

- `docs/technical_specification.md` - product and engineering specification
- `src/spaced_repetition_bot` - application source code
- `tests` - unit tests for the core review flow

## Stack

- `Python 3.12+`
- `aiogram 3.x`
- `FastAPI`
- `Pydantic v2`
- `SQLAlchemy 2.x`

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

Install the runtime dependencies:

```bash
python3 -m pip install --upgrade pip
python3 -m pip install -e .
```

Install the full development toolchain:

```bash
python3 -m pip install -e ".[db,quality]"
```

Install local Git hooks:

```bash
python3 -m pip install pre-commit
pre-commit install --hook-type pre-push
```

### 5. Configure the Environment

Create a local `.env` file from the template:

```bash
cp .env.example .env
```

Example configuration:

```env
SRB_APP_NAME=Spaced Repetition Bot
SRB_APP_VERSION=0.1.0
SRB_API_PREFIX=/api/v1
SRB_DEBUG=false
SRB_TELEGRAM_BOT_TOKEN=change-me
SRB_TRANSLATOR_PROVIDER=mock
```

Notes:

- `mock` is the default translation provider for local development
- no external translation API key is required for the current MVP
- replace `SRB_TELEGRAM_BOT_TOKEN` before starting the Telegram bot

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
    "source_lang": "en",
    "target_lang": "es",
    "learn": true
  }'
```

With the default `mock` provider, the translation response is deterministic.

### 8. Start the Telegram Bot

Set a real token in `.env`:

```env
SRB_TELEGRAM_BOT_TOKEN=<your-token>
```

Start long polling:

```bash
python3 -m spaced_repetition_bot.run_telegram_bot
```

Supported commands:

- `/start`
- `/history`
- `/progress`

Any plain text message is treated as a translation request.

### 9. Run Tests

```bash
python3 -m pytest -q
```

### 10. Check Syntax

```bash
python3 -m compileall src tests
```

### 11. Run Quality Checks

```bash
flake8 src tests
radon cc -a -s src
python3 scripts/check_complexity.py src/ --max 9
radon mi -s src
bandit -r src -lll
pytest --maxfail=0 --cov=src --cov-report=term-missing --cov-fail-under=80
HOME=$PWD/.safety-home safety check
locust --headless --host=http://localhost:8000 --users=100 --spawn-rate=10 --run-time=5m --csv=results --html report.html
```

OpenAPI quality is enforced by the API test suite. The schema must keep
non-empty operation and parameter descriptions, plus at least one documented
response example for every request.

## Quality Gates

- `Pre-push`: `pre-commit` blocks pushes on any `flake8` error and on any
  high-severity `bandit` finding in staged source files.
- `Pre-merge`: GitHub Actions blocks PRs on failed tests, coverage below `80%`,
  failed quality/security gates, or missing OpenAPI contract checks.
- `Release`: run the full CI pipeline and a local demo smoke test before
  presenting the project.

Repository settings still need one external GitHub branch-protection rule:
require at least one approval from someone other than the PR author.

## Troubleshooting

### `spaced_repetition_bot` cannot be imported

The project is not installed in the current environment:

```bash
python3 -m pip install -e .
```

### `ModuleNotFoundError: No module named pydantic_settings`

Dependencies are missing or the wrong environment is active:

```bash
python3 -m pip install -e ".[db,quality]"
```

### The Telegram bot does not respond

Check the following:

- the virtual environment is active
- `SRB_TELEGRAM_BOT_TOKEN` is set in `.env`
- the token is not still `change-me`
- the bot is running in a separate process from `uvicorn`

### `uvicorn` is not found

Install the project in the current environment:

```bash
python3 -m pip install -e .
```

## Useful Files

- `docs/technical_specification.md` - full specification
- `.env.example` - environment template
- `locustfile.py` - performance test scenarios
- `scripts/check_complexity.py` - cyclomatic complexity gate
- `src/spaced_repetition_bot/main.py` - FastAPI entrypoint
- `src/spaced_repetition_bot/run_telegram_bot.py` - Telegram polling entrypoint

## Quality Commands

```bash
python3 -m compileall src tests
pytest --cov=src --cov-report=term-missing --cov-fail-under=80
flake8 src tests
radon cc -a -s src
radon mi -s src
bandit -r src
safety check
```
