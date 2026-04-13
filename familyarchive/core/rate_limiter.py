"""
Reusable fixed-interval rate limiter.

Thread-safe, configurable RPM, pure Python. Use for any API that
has rate limits (Gemini, OpenAI, Anthropic, AssemblyAI).
"""

import time
import threading


class RateLimiter:
    """Fixed-interval rate limiter. Spaces requests evenly to stay within RPM.

    Usage:
        limiter = RateLimiter(requests_per_minute=400)
        limiter.acquire()  # blocks until a request slot is available
    """

    def __init__(self, requests_per_minute=400):
        if requests_per_minute <= 0:
            raise ValueError("requests_per_minute must be positive")
        self.requests_per_minute = requests_per_minute
        self._interval = 60.0 / requests_per_minute
        self._lock = threading.Lock()
        self._next_allowed = time.monotonic()

    def acquire(self):
        """Block until a request token is available."""
        with self._lock:
            now = time.monotonic()
            if now < self._next_allowed:
                sleep_time = self._next_allowed - now
                self._next_allowed += self._interval
            else:
                sleep_time = 0
                self._next_allowed = now + self._interval

        if sleep_time > 0:
            time.sleep(sleep_time)
