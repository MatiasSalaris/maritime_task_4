"""A swarm-wide gate that serialises and spaces the agents' LLM calls.

The dominant constraint is the shared Groq budget (~6000 tokens/minute on the
free tier). Three agents calling independently let the first one monopolise the
budget while the others got nothing but 429s. This gate makes the agents share
the channel fairly:

  * only ONE LLM call is in flight at a time (acquire an asyncio lock), and
  * successive calls are spaced at least ``min_spacing_s`` apart,

so the per-minute token rate stays under the cap and every agent gets a turn.
The lock is FIFO, so an agent that just thought queues behind its peers rather
than barging back in. This also makes the live reasoning legible: thoughts
stream one asset at a time instead of three at once.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time

logger = logging.getLogger(__name__)


class LLMGate:
    def __init__(self, min_spacing_s: float = 9.0) -> None:
        self.min_spacing_s = max(0.0, min_spacing_s)
        self._lock = asyncio.Lock()
        self._next_allowed = 0.0

    @contextlib.asynccontextmanager
    async def slot(self, agent_id: str = "", urgent: bool = False):
        """Acquire the single LLM slot, waiting out the inter-call spacing.

        ``urgent`` (e.g. a fresh contact) skips the spacing wait so the asset
        reacts immediately — it still serialises behind any in-flight call.
        """
        async with self._lock:
            wait = self._next_allowed - time.monotonic()
            if wait > 0 and not urgent:
                await asyncio.sleep(wait)
            try:
                yield
            finally:
                # Space the NEXT call from the moment this one finished.
                self._next_allowed = time.monotonic() + self.min_spacing_s
