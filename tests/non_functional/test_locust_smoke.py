"""Smoke tests for lightweight non-functional checks."""

from __future__ import annotations

import importlib
import sys
import types

import pytest

pytestmark = pytest.mark.slow


class FakeStats:
    """Locust stats stub."""

    def __init__(self, num_requests: int, p95: float) -> None:
        self.num_requests = num_requests
        self._p95 = p95

    def get_response_time_percentile(self, _percentile: float) -> float:
        return self._p95


class FakeEnvironment:
    """Locust environment stub."""

    def __init__(self, stats) -> None:
        self.stats = type("StatsHolder", (), {"total": stats})()
        self.process_exit_code: int | None = None


@pytest.fixture
def locustfile_module(monkeypatch):
    """Import locustfile against a tiny locust stub."""

    class DummyEvents:
        class quitting:
            @staticmethod
            def add_listener(func):
                return func

    fake_locust = types.SimpleNamespace(
        HttpUser=type("HttpUser", (), {}),
        between=lambda *_args, **_kwargs: None,
        events=DummyEvents,
        task=lambda weight=1: (lambda func: func),
    )

    monkeypatch.setitem(sys.modules, "locust", fake_locust)
    sys.modules.pop("locustfile", None)
    return importlib.import_module("locustfile")


def test_locust_threshold_sets_failure_when_no_requests(locustfile_module) -> None:
    environment = FakeEnvironment(FakeStats(num_requests=0, p95=0.0))

    locustfile_module.check_p95_threshold(environment)

    assert environment.process_exit_code == 1


def test_locust_threshold_sets_failure_when_p95_exceeds_limit(
    locustfile_module,
) -> None:
    environment = FakeEnvironment(
        FakeStats(num_requests=10, p95=locustfile_module.P95_THRESHOLD_MS + 1)
    )

    locustfile_module.check_p95_threshold(environment)

    assert environment.process_exit_code == 1


def test_locust_threshold_keeps_success_when_p95_is_under_limit(
    locustfile_module,
) -> None:
    environment = FakeEnvironment(FakeStats(num_requests=10, p95=42.0))

    locustfile_module.check_p95_threshold(environment)

    assert environment.process_exit_code is None
