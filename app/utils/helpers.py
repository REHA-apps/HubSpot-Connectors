# app/utils/helpers.py
from __future__ import annotations

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.logging import CorrelationAdapter, get_logger

logger = get_logger("utils.http")


class HTTPClient:
    """Singleton-like async HTTP client with correlation-ID aware logging."""

    _client: httpx.AsyncClient | None = None

    @classmethod
    def get_client(cls, *, corr_id: str | None = None) -> httpx.AsyncClient:
        log = CorrelationAdapter(logger, corr_id or "no-corr-id")

        if cls._client is None or cls._client.is_closed:
            log.info("Creating new shared AsyncClient instance")
            cls._client = httpx.AsyncClient(timeout=30.0)
        else:
            log.debug("Reusing existing shared AsyncClient instance")

        return cls._client

    @classmethod
    async def close(cls, *, corr_id: str | None = None) -> None:
        log = CorrelationAdapter(logger, corr_id or "no-corr-id")

        if cls._client and not cls._client.is_closed:
            log.info("Closing shared AsyncClient instance")
            await cls._client.aclose()
            cls._client = None
        else:
            log.debug("AsyncClient already closed or not initialized")


def hubspot_retry():
    """Tenacity retry decorator for HubSpot API calls.
    Retries on HTTPStatusError with exponential backoff.
    """
    return retry(
        wait=wait_exponential(multiplier=1, min=4, max=10),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type(httpx.HTTPStatusError),
        reraise=True,
    )
