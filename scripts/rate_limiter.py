"""
Reusable token bucket rate limiter.

Thread-safe, configurable RPM, pure Python. Use for any API that
has rate limits (Gemini, OpenAI, Anthropic, AssemblyAI).
"""

import time
import threading


class RateLimiter:
    """Token bucket rate limiter.

    Usage:
        limiter = RateLimiter(requests_per_minute=400)
        limiter.acquire()  # blocks until a token is available
    """

    def __init__(self, requests_per_minute=400):
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
