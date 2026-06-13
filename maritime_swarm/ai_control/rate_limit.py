"""A shared client-side token-bucket limiter.

All three agent brains run in one process, so they can share one limiter that
paces LLM calls to stay UNDER the provider's tokens-per-minute limit. This turns
"three simultaneous requests → server 429 lockout (minutes)" into "bursts pass
when the bucket is full, otherwise agents briefly wait their turn" — every agent
still gets to act, and we never drive the server bucket negative.

Sized below Groq's free tier (≈6000 tokens/min ≈100/s) with margin.
"""

from __future__ import annotations

import asyncio
import time


class RateLimiter:
    def __init__(
        self,
        capacity: float = 5500.0,
        refill_per_s: float = 85.0,
        initial: float = 1500.0,
        budget_fn=None,
    ) -> None:
        self.capacity = capacity
        self.refill = refill_per_s
        # Start at ~one call's worth: lets a single "probe" call go out to learn
        # the server's real budget, then we pace accurately from its headers.
        self.tokens = min(initial, capacity)
        self._t = time.monotonic()
        self._lock = asyncio.Lock()
        self._budget_fn = budget_fn   # returns the server's last remaining-tokens, or None

    async def acquire(self, n: float) -> None:
        """Block until ~n tokens are available, then consume (FIFO/paced).

        Never assumes more than the server's last reported remaining tokens, so
        the swarm doesn't drive the provider bucket negative into a lockout.
        """
        n = min(n, self.capacity)
        async with self._lock:
            while True:
                now = time.monotonic()
                self.tokens = min(self.capacity, self.tokens + (now - self._t) * self.refill)
                self._t = now
                if self._budget_fn is not None:
                    srv = self._budget_fn()
                    if srv is not None:
                        self.tokens = min(self.tokens, srv)   # trust the server's truth
                if self.tokens >= n:
                    self.tokens -= n
                    return
                await asyncio.sleep(min(max((n - self.tokens) / self.refill, 0.5), 5.0))


class NullLimiter:
    """No-op limiter (offline heuristic decider / no real LLM)."""

    async def acquire(self, n: float) -> None:
        return
