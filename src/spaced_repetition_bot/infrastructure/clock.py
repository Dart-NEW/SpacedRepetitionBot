"""Time utilities."""

from datetime import datetime, timezone


class SystemClock:
    """System-backed clock adapter."""

    def now(self) -> datetime:
        """Return current UTC time."""

        return datetime.now(timezone.utc)
