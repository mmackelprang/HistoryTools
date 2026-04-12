"""
Tests for the rate limiter module (scripts/rate_limiter.py).
"""

import time
import threading

import pytest

from scripts.rate_limiter import RateLimiter


class TestRateLimiter:
    """Test token bucket rate limiter."""

    def test_acquire_succeeds_immediately_when_tokens_available(self):
        limiter = RateLimiter(requests_per_minute=600)  # 10 per second
        start = time.monotonic()
        limiter.acquire()
        elapsed = time.monotonic() - start
        assert elapsed < 0.1  # should be nearly instant

    def test_acquire_blocks_when_tokens_exhausted(self):
        limiter = RateLimiter(requests_per_minute=60)  # 1 per second
        limiter.acquire()  # use the initial token
        start = time.monotonic()
        limiter.acquire()  # should wait ~1 second
        elapsed = time.monotonic() - start
        assert elapsed >= 0.8  # allow some tolerance

    def test_multiple_acquires_within_rate(self):
        limiter = RateLimiter(requests_per_minute=6000)  # 100 per second
        for _ in range(10):
            limiter.acquire()
        # Should complete very quickly at this rate

    def test_thread_safety(self):
        limiter = RateLimiter(requests_per_minute=6000)
        results = []

        def worker():
            limiter.acquire()
            results.append(True)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        assert len(results) == 20

    def test_custom_rpm(self):
        limiter = RateLimiter(requests_per_minute=120)
        assert limiter.requests_per_minute == 120
