"""Runtime wiring and export tests."""

from __future__ import annotations

import asyncio
from importlib import import_module

import pytest

from spaced_repetition_bot import application
from spaced_repetition_bot.bootstrap import (
    build_container,
    build_translation_provider,
)
from spaced_repetition_bot.infrastructure.clock import SystemClock
from spaced_repetition_bot.infrastructure.config import AppConfig
from spaced_repetition_bot.application.dtos import (
    GetHistoryQuery,
    TranslatePhraseCommand,
)
from spaced_repetition_bot.infrastructure.translators import (
    MockTranslationProvider,
    YandexTranslationProvider,
)
from spaced_repetition_bot.main import create_app
from spaced_repetition_bot.presentation import (
    build_api_router,
    build_telegram_router,
)
from tests.support import build_test_container

pytestmark = pytest.mark.integration


def test_app_config_reads_environment(monkeypatch) -> None:
    monkeypatch.setenv("SRB_APP_NAME", "Quality Gate Bot")
    monkeypatch.setenv("SRB_APP_VERSION", "1.2.3")
    monkeypatch.setenv("SRB_API_PREFIX", "/api/quality")

    config = AppConfig()

    assert config.app_name == "Quality Gate Bot"
    assert config.app_version == "1.2.3"
    assert config.api_prefix == "/api/quality"


def test_system_clock_returns_timezone_aware_utc_datetime() -> None:
    assert SystemClock().now().tzinfo is not None


def test_build_translation_provider_covers_mock_yandex_and_missing_config(
) -> None:
    assert isinstance(
        build_translation_provider(AppConfig(translation_provider="mock")),
        MockTranslationProvider,
    )
    with pytest.raises(ValueError, match="SRB_YANDEX_TRANSLATE_API_KEY"):
        build_translation_provider(
            AppConfig(
                translation_provider="yandex",
                yandex_folder_id="folder",
            )
        )
    with pytest.raises(ValueError, match="SRB_YANDEX_FOLDER_ID"):
        build_translation_provider(
            AppConfig(
                translation_provider="yandex",
                yandex_translate_api_key="key",
            )
        )

    provider = build_translation_provider(
        AppConfig(
            translation_provider="yandex",
            yandex_translate_api_key="key",
            yandex_folder_id="folder",
        )
    )

    assert isinstance(provider, YandexTranslationProvider)


def test_build_container_wires_runtime_use_cases_against_shared_repositories(
) -> None:
    container = build_container(
        AppConfig(
            app_name="Test App",
            app_version="2.0.0",
            api_prefix="/api/test",
            database_url="sqlite:///:memory:",
        )
    )

    translation = container.translate_phrase.execute(
        TranslatePhraseCommand(user_id=1, text="hello")
    )
    history = container.get_history.execute(GetHistoryQuery(user_id=1))

    assert history[0].card_id == translation.card_id
    assert container.reminder_service.poll_interval_seconds == 60
    container.settings_repository.session_factory.kw["bind"].dispose()


def test_create_app_registers_prefixed_routes_and_metadata(
    monkeypatch,
) -> None:
    container = build_test_container(SystemClock().now())
    monkeypatch.setattr(
        "spaced_repetition_bot.main.build_container",
        lambda: container,
    )

    app = create_app()
    route_paths = {route.path for route in app.routes}

    assert app.title == "Test App"
    assert app.version == "9.9.9"
    assert "/api/test/health" in route_paths


def test_run_telegram_bot_starts_polling_and_cancels_reminders(
    monkeypatch,
) -> None:
    from spaced_repetition_bot import run_telegram_bot

    events: dict[str, object] = {}
    container = build_test_container(SystemClock().now())

    class FakeBot:
        def __init__(self, token: str) -> None:
            events["token"] = token

    class FakeDispatcher:
        def include_router(self, router: object) -> None:
            events["router"] = router

        async def start_polling(self, bot: object) -> None:
            events["bot"] = bot

    class FakeTask:
        cancelled = False

        def cancel(self) -> None:
            self.cancelled = True

        def __await__(self):
            async def _result():
                return None

            return _result().__await__()

    async def fake_reminder_run(_self, _bot) -> None:
        return None

    fake_task = FakeTask()

    monkeypatch.setattr(run_telegram_bot, "build_container", lambda: container)
    monkeypatch.setattr(run_telegram_bot, "Bot", FakeBot)
    monkeypatch.setattr(run_telegram_bot, "Dispatcher", FakeDispatcher)
    monkeypatch.setattr(
        run_telegram_bot,
        "build_telegram_router",
        lambda _container: object(),
    )
    monkeypatch.setattr(
        type(container.reminder_service),
        "run",
        fake_reminder_run,
    )

    def fake_create_task(coroutine):
        coroutine.close()
        return fake_task

    monkeypatch.setattr(asyncio, "create_task", fake_create_task)

    asyncio.run(run_telegram_bot.run())

    assert events["token"] == "test-token"
    assert fake_task.cancelled is True


def test_run_telegram_bot_main_delegates_to_asyncio_run(monkeypatch) -> None:
    from spaced_repetition_bot import run_telegram_bot

    called: dict[str, object] = {}

    def fake_run(coroutine) -> None:
        called["coroutine"] = coroutine
        coroutine.close()

    monkeypatch.setattr(run_telegram_bot.asyncio, "run", fake_run)

    run_telegram_bot.main()

    assert called["coroutine"].cr_code.co_name == "run"


def test_public_exports_point_to_canonical_runtime_modules() -> None:
    assert application.TranslatePhraseUseCase is import_module(
        "spaced_repetition_bot.application.use_cases"
    ).TranslatePhraseUseCase
    assert callable(build_api_router)
    assert callable(build_telegram_router)


@pytest.mark.parametrize(
    "module_name",
    [
        "spaced_repetition_bot.application.dto_history",
        "spaced_repetition_bot.application.dto_progress",
        "spaced_repetition_bot.application.dto_reviews",
        "spaced_repetition_bot.application.dto_settings",
        "spaced_repetition_bot.application.dto_translation",
        "spaced_repetition_bot.application.history_use_case",
        "spaced_repetition_bot.application.progress_use_case",
        "spaced_repetition_bot.application.review_use_cases",
        "spaced_repetition_bot.application.settings_use_case",
        "spaced_repetition_bot.application.toggle_learning_command",
        "spaced_repetition_bot.application.toggle_learning_use_case",
        "spaced_repetition_bot.application.translation_use_case",
        "spaced_repetition_bot.application.use_case_common",
        "spaced_repetition_bot.presentation.api_due_reviews",
        "spaced_repetition_bot.presentation.api_errors",
        "spaced_repetition_bot.presentation.api_health",
        "spaced_repetition_bot.presentation.api_history",
        "spaced_repetition_bot.presentation.api_history_models",
        "spaced_repetition_bot.presentation.api_learning",
        "spaced_repetition_bot.presentation.api_learning_models",
        "spaced_repetition_bot.presentation.api_progress",
        "spaced_repetition_bot.presentation.api_progress_models",
        "spaced_repetition_bot.presentation.api_review_models",
        "spaced_repetition_bot.presentation.api_settings",
        "spaced_repetition_bot.presentation.api_settings_models",
        "spaced_repetition_bot.presentation.api_submit_review",
        "spaced_repetition_bot.presentation.api_translation_models",
        "spaced_repetition_bot.presentation.api_translations",
    ],
)
def test_removed_split_modules_are_no_longer_importable(
    module_name: str,
) -> None:
    with pytest.raises(ModuleNotFoundError):
        import_module(module_name)
