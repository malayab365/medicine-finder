"""A small in-process fixed-window rate limiter.

Kept dependency-free and in-memory, consistent with the hand-rolled cache. It's
per-process, so behind multiple workers each worker enforces its own window —
good enough to shield the paid LLM endpoint at v1 scale. Move to a shared store
(e.g. Redis) if you need global limits.
"""

import threading
import time
from collections.abc import Callable

from fastapi import HTTPException, Request


class FixedWindowRateLimiter:
    def __init__(self, limit: int, window: float = 60.0):
        self.limit = limit
        self.window = window
        self._hits: dict[str, tuple[float, int]] = {}
        # FastAPI runs sync dependencies in a threadpool, so `check` can be called
        # from multiple threads concurrently. Guard the read-modify-write on _hits.
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, int]:
        """Record a hit for `key`. Returns (allowed, retry_after_seconds)."""
        now = time.monotonic()
        with self._lock:
            start, count = self._hits.get(key, (now, 0))
            if now - start >= self.window:
                start, count = now, 0
            count += 1
            self._hits[key] = (start, count)
        if count > self.limit:
            return False, int(self.window - (now - start)) + 1
        return True, 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def rate_limit(limiter: FixedWindowRateLimiter) -> Callable[[Request], None]:
    """Build a FastAPI dependency that enforces `limiter` per client IP."""

    def dependency(request: Request) -> None:
        key = request.client.host if request.client else "unknown"
        allowed, retry_after = limiter.check(key)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please slow down.",
                headers={"Retry-After": str(retry_after)},
            )

    return dependency
