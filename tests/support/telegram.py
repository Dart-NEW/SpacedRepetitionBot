"""Telegram-layer doubles for tests."""

from __future__ import annotations

from dataclasses import dataclass, field

from spaced_repetition_bot.bootstrap import ApplicationContainer
from spaced_repetition_bot.presentation.telegram import build_telegram_router


@dataclass(slots=True)
class FakeUser:
    """Minimal Telegram user stub."""

    id: int


@dataclass(slots=True)
class FakeMessage:
    """Minimal Telegram message stub."""

    from_user: FakeUser | None
    text: str | None = None
    answers: list[str] = field(default_factory=list)

    async def answer(self, text: str, **_kwargs) -> None:
        self.answers.append(text)


@dataclass(slots=True)
class FakeBot:
    """Minimal bot stub used by reminder tests."""

    sent_messages: list[tuple[int, str]] = field(default_factory=list)
    raise_on_send: bool = False

    async def send_message(self, user_id: int, text: str, **_kwargs) -> None:
        if self.raise_on_send:
            raise RuntimeError("simulated bot failure")
        self.sent_messages.append((user_id, text))


def handler_callbacks(
    container: ApplicationContainer,
) -> dict[str, object]:
    """Return telegram handler callbacks keyed by function name."""

    router = build_telegram_router(container)
    return {
        handler.callback.__name__: handler.callback
        for handler in router.message.handlers
    }
