"""Locust scenarios for local API performance checks."""

from __future__ import annotations

import itertools

from locust import HttpUser, between, events, task

P95_THRESHOLD_MS = 300.0
USER_COUNTER = itertools.count(1)
PHRASE_COUNTER = itertools.count(1)


class SpacedRepetitionUser(HttpUser):
    """Basic user behavior against the MVP API."""

    wait_time = between(0.1, 0.5)

    def on_start(self) -> None:
        self.user_id = next(USER_COUNTER)
        self.client.put(
            "/api/v1/settings",
            name="PUT /api/v1/settings",
            json={
                "user_id": self.user_id,
                "default_source_lang": "en",
                "default_target_lang": "es",
                "timezone": "UTC",
                "notification_time_local": "09:00:00",
                "notifications_enabled": True,
            },
        )

    @task(4)
    def create_translation(self) -> None:
        phrase_number = next(PHRASE_COUNTER)
        self.client.post(
            "/api/v1/translations",
            name="POST /api/v1/translations",
            json={
                "user_id": self.user_id,
                "text": f"phrase {phrase_number}",
                "source_lang": "en",
                "target_lang": "es",
                "learn": True,
            },
        )

    @task(2)
    def get_history(self) -> None:
        self.client.get(
            "/api/v1/history",
            name="GET /api/v1/history",
            params={"user_id": self.user_id, "limit": 10},
        )

    @task(2)
    def get_progress(self) -> None:
        self.client.get(
            "/api/v1/progress",
            name="GET /api/v1/progress",
            params={"user_id": self.user_id},
        )

    @task(1)
    def get_due_reviews(self) -> None:
        self.client.get(
            "/api/v1/reviews/due",
            name="GET /api/v1/reviews/due",
            params={"user_id": self.user_id},
        )

    @task(1)
    def get_settings(self) -> None:
        self.client.get(
            "/api/v1/settings",
            name="GET /api/v1/settings",
            params={"user_id": self.user_id},
        )


@events.quitting.add_listener
def check_p95_threshold(environment, **_kwargs) -> None:
    """Fail the Locust run when the total P95 exceeds the threshold."""

    total_stats = environment.stats.total
    if total_stats.num_requests == 0:
        print("No requests were recorded during the Locust run.")
        environment.process_exit_code = 1
        return

    p95 = total_stats.get_response_time_percentile(0.95) or 0.0
    print(f"Observed total P95 response time: {p95:.2f} ms")
    if p95 >= P95_THRESHOLD_MS:
        print(
            f"P95 response time {p95:.2f} ms exceeds the threshold of "
            f"{P95_THRESHOLD_MS:.0f} ms."
        )
        environment.process_exit_code = 1
