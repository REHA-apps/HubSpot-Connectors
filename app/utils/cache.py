import asyncio
import time
from collections.abc import Callable, Coroutine
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class AsyncTTL(Generic[T]):  # noqa: UP046
    """Description:
        A simple asynchronous in-memory LRU-like cache with Time-To-Live (TTL).

    Rules Applied:
        - Thread-safe (via asyncio.Lock).
        - Supports optimistic fetching (get_or_fetch) with per-key coalescing.
        - Allows manual invalidation.
    """

    def __init__(self, ttl: int = 300, max_size: int = 1024):
        self.ttl = ttl
        self.max_size = max_size
        self._cache: dict[str, tuple[T, float]] = {}
        self._lock = asyncio.Lock()
        self._inflight: dict[str, asyncio.Event] = {}

    async def get_or_fetch(
        self, key: str, fetcher: Callable[[], Coroutine[Any, Any, T]]
    ) -> T:
        """Retrieve value from cache if valid, otherwise execute fetcher and
        cache result.

        Uses per-key coalescing: if multiple coroutines request the same key
        concurrently, only the first one fetches; the rest wait for the result.
        """
        async with self._lock:
            # 1. Cache hit — return immediately
            if key in self._cache:
                value, timestamp = self._cache[key]
                if time.time() - timestamp < self.ttl:
                    return value
                else:
                    del self._cache[key]

            # 2. Another coroutine is already fetching this key — wait for it
            if key in self._inflight:
                event = self._inflight[key]
                # Release the lock while waiting
            else:
                # 3. We are the first — create an Event and fetch
                event = asyncio.Event()
                self._inflight[key] = event
                event = None  # sentinel: we are the fetcher

        if event is not None:
            # Wait for the fetcher to complete, then return from cache
            await event.wait()
            async with self._lock:
                if key in self._cache:
                    return self._cache[key][0]
            # Fetcher failed or returned None — fall through and try ourselves
            return await self._do_fetch(key, fetcher)

        # We are the designated fetcher
        return await self._do_fetch(key, fetcher)

    async def _do_fetch(
        self, key: str, fetcher: Callable[[], Coroutine[Any, Any, T]]
    ) -> T:
        """Execute fetcher, cache the result, and notify waiters."""
        event = None
        try:
            async with self._lock:
                if key not in self._inflight:
                    self._inflight[key] = asyncio.Event()
                event = self._inflight[key]

            value = await fetcher()

            if value is not None:
                async with self._lock:
                    if len(self._cache) >= self.max_size:
                        self._cache.popitem()
                    self._cache[key] = (value, time.time())

            return value
        finally:
            async with self._lock:
                self._inflight.pop(key, None)
            if event is not None:
                event.set()

    async def get(self, key: str) -> T | None:
        async with self._lock:
            if key in self._cache:
                value, timestamp = self._cache[key]
                if time.time() - timestamp < self.ttl:
                    return value
                del self._cache[key]
        return None

    async def set(self, key: str, value: T) -> None:
        """Manually populate the cache with a known value."""
        async with self._lock:
            if len(self._cache) >= self.max_size:
                self._cache.popitem()
            self._cache[key] = (value, time.time())

    async def invalidate(self, key: str) -> None:
        async with self._lock:
            self._cache.pop(key, None)

    async def clear(self) -> None:
        async with self._lock:
            self._cache.clear()
