"""Login throttling (spec section 7: "generic failure and throttling").

Counts failed logins per (client IP, email) in a sliding window. Kept in memory: fine for
the single-process demo deployment; with several API processes each one counts separately
(a shared store such as a database table would be needed then).
"""

import threading
import time
from collections import defaultdict, deque

from app.core.config import get_settings


class LoginRateLimiter:
    def __init__(self, max_failures: int, window_seconds: int):
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._failures: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: tuple[str, str], now: float) -> deque[float]:
        attempts = self._failures[key]
        while attempts and now - attempts[0] > self.window_seconds:
            attempts.popleft()
        return attempts

    def is_blocked(self, ip: str, email: str) -> bool:
        key = (ip, email.lower())
        with self._lock:
            return len(self._prune(key, time.monotonic())) >= self.max_failures

    def record_failure(self, ip: str, email: str) -> None:
        key = (ip, email.lower())
        with self._lock:
            self._prune(key, time.monotonic()).append(time.monotonic())

    def reset(self, ip: str, email: str) -> None:
        with self._lock:
            self._failures.pop((ip, email.lower()), None)

    def clear(self) -> None:
        with self._lock:
            self._failures.clear()


_settings = get_settings()
login_rate_limiter = LoginRateLimiter(_settings.login_max_failures, _settings.login_failure_window_seconds)
