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
    """Shared async HTTP client with:
    - correlation-ID aware logging
    - global timeout
    - connection pooling
    - request/response logging hooks
    """

    _client: httpx.AsyncClient | None = None

    @classmethod
    def get_client(cls, *, corr_id: str | None = None) -> httpx.AsyncClient:
        log = CorrelationAdapter(logger, corr_id or "no-corr-id")

        if cls._client is None or cls._client.is_closed:
            log.info("Creating new shared AsyncClient instance")

            cls._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                event_hooks={
                    "request": [cls._log_request(corr_id)],
                    "response": [cls._log_response(corr_id)],
                },
            )
        else:
            log.debug("Reusing existing shared AsyncClient instance")

        return cls._client

    # ---------------------------------------------------------
    # Logging hooks
    # ---------------------------------------------------------
    @staticmethod
    def _log_request(corr_id: str | None):
        def hook(request: httpx.Request):
            log = CorrelationAdapter(logger, corr_id or "no-corr-id")
            log.info("HTTP %s %s", request.method, request.url)

        return hook

    @staticmethod
    def _log_response(corr_id: str | None):
        def hook(response: httpx.Response):
            log = CorrelationAdapter(logger, corr_id or "no-corr-id")
            log.info(
                "HTTP %s %s → %s",
                response.request.method,
                response.request.url,
                response.status_code,
            )

        return hook

    # ---------------------------------------------------------
    # Shutdown
    # ---------------------------------------------------------
    @classmethod
    async def close(cls, *, corr_id: str | None = None) -> None:
        log = CorrelationAdapter(logger, corr_id or "no-corr-id")

        if cls._client and not cls._client.is_closed:
            log.info("Closing shared AsyncClient instance")
            await cls._client.aclose()  
            cls._client = None
        else:
            log.debug("AsyncClient already closed or not initialized")


# ---------------------------------------------------------
# Retry helpers
# ---------------------------------------------------------
def hubspot_retry():
    """Retry HubSpot API calls on transient errors."""
    return retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type(
            (
                httpx.HTTPStatusError,
                httpx.ConnectError,
                httpx.ReadTimeout,
                httpx.RemoteProtocolError,
            )
        ),
        reraise=True,
    )


def slack_retry():
    """Retry Slack API calls on transient errors."""
    return retry(
        wait=wait_exponential(multiplier=1, min=1, max=8),
        stop=stop_after_attempt(4),
        retry=retry_if_exception_type(
            (
                httpx.HTTPStatusError,
                httpx.ConnectError,
                httpx.ReadTimeout,
            )
        ),
        reraise=True,
    )
