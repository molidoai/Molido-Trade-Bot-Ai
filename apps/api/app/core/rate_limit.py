"""Simple in-memory rate limiter for API (per-IP). Not a substitute for edge WAF."""

from __future__ import annotations
import time
from collections import defaultdict
from threading import Lock


class RateLimiter:
    def __init__(self, max_calls: int = 120, window_seconds: float = 60.0):
        self.max_calls = max_calls
        self.window = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            stamps = self._hits[key]
            self._hits[key] = [t for t in stamps if now - t < self.window]
            if len(self._hits[key]) >= self.max_calls:
                return False
            self._hits[key].append(now)
            return True


limiter = RateLimiter()
