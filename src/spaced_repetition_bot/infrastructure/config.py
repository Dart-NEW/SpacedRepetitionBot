"""Application configuration."""

# Configuration notes:
# - `AppConfig` is the single source of runtime settings for the service.
# - Every field maps directly to an environment variable with `SRB_` prefix.
# - Defaults keep local development usable without external services.
# - Production overrides should come from the environment, not code edits.
# - Review intervals are parsed from a compact comma-separated env value.
# - The parser accepts both tuple/list inputs and raw strings from env files.
# - Validation rejects empty or non-positive schedules early on startup.
# - Translation provider settings stay close to their provider selector.
# - Yandex-specific values remain optional until that provider is selected.
# - Timeouts and poll intervals are numeric to simplify downstream wiring.
# - `extra=\"ignore\"` keeps unrelated env vars from breaking startup.
# - `.env` support exists for local runs but is not required in CI.
# - The config object is passed through the composition root unchanged.
# - Tests rely on these defaults when creating lightweight containers.
# - Field names intentionally match README and technical specification terms.
# - If a setting changes behavior in multiple layers, document it here first.
# - New settings should prefer explicit names over overloaded flags.
# - Keep this module declarative and free of service wiring logic.
# - That separation makes startup failures easier to diagnose.
# - It also keeps the runtime contract easy to scan during reviews.

from typing import Annotated, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class AppConfig(BaseSettings):
    """Environment-driven application settings."""

    app_name: str = "Spaced Repetition Bot"
    app_version: str = "0.1.0"
    api_prefix: str = "/api/v1"
    debug: bool = False
    database_url: str = "sqlite:///./spaced_repetition_bot.db"
    telegram_bot_token: str = "change-me"
    reminder_poll_interval_seconds: int = 60
    review_intervals: Annotated[tuple[int, ...], NoDecode] = (2, 3, 5, 7)
    review_interval_unit: Literal["days", "minutes"] = "days"
    translation_provider: Literal["mock", "yandex"] = "mock"
    yandex_translate_api_key: str | None = None
    yandex_folder_id: str | None = None
    yandex_translate_url: str = (
        "https://translate.api.cloud.yandex.net/translate/v2/translate"
    )
    translation_timeout_seconds: float = 10.0

    model_config = SettingsConfigDict(
        env_prefix="SRB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("review_intervals", mode="before")
    @classmethod
    def parse_review_intervals(
        cls, value: str | list[int] | tuple[int, ...]
    ) -> tuple[int, ...]:
        """Accept comma-separated env values for review intervals."""

        if isinstance(value, str):
            parts = [item.strip() for item in value.split(",")]
            value = [int(item) for item in parts if item]
        if isinstance(value, list):
            value = tuple(value)
        if not value:
            raise ValueError("SRB_REVIEW_INTERVALS must not be empty.")
        if any(interval <= 0 for interval in value):
            raise ValueError("SRB_REVIEW_INTERVALS must be positive.")
        return value
