"""Application configuration."""

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

    model_config = SettingsConfigDict(
        env_prefix="SRB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
