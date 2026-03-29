"""Application configuration."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    """Environment-driven application settings."""

    app_name: str = "Spaced Repetition Bot"
    app_version: str = "0.1.0"
    api_prefix: str = "/api/v1"
    debug: bool = False
    database_url: str = "sqlite:///./spaced_repetition_bot.db"
    telegram_bot_token: str = "change-me"
    reminder_poll_interval_seconds: int = 60
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
