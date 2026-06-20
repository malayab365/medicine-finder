"""A small in-process fixed-window rate limiter.

Kept dependency-free and in-memory, consistent with the hand-rolled cache. It's
per-process, so behind multiple workers each worker enforces its own window —
good enough to shield the paid LLM endpoint at v1 scale. Move to a shared store
(e.g. Redis) if you need global limits.
"""

import time


class FixedWindowRateLimiter:
    def __init__(self, limit: int, window: float = 60.0):
        self.limit = limit
        self.window = window
        self._hits: dict[str, tuple[float, int]] = {}

    def check(self, key: str) -> tuple[bool, int]:
        """Record a hit for `key`. Returns (allowed, retry_after_seconds)."""
        now = time.monotonic()
        start, count = self._hits.get(key, (now, 0))
        if now - start >= self.window:
            start, count = now, 0
        count += 1
        self._hits[key] = (start, count)
        if count > self.limit:
            return False, int(self.window - (now - start)) + 1
        return True, 0

    def reset(self) -> None:
        self._hits.clear()
