# app/clients/base_client.py
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx
import asyncio
import random

from app.core.logging import CorrelationAdapter, get_logger
from app.utils.constants import ErrorCode
from fastapi import Depends

logger = get_logger("base_client")


class BaseClient:
    """Base async client for external APIs.

    Features:
    - Shared httpx.AsyncClient (connection pooling)
    - Correlation ID support
    - Structured logging
    - Python 3.12 typing
    - Safe error handling
    - Optional retry support (hook-ready)
    """

    _client: httpx.AsyncClient | None = None

    def __init__(
        self,
        base_url: str,
        headers: Mapping[str, str] | None = None,
        corr_id: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = dict(headers or {})
        self.corr_id = corr_id or "client_unknown"
        self.log = CorrelationAdapter(logger, self.corr_id)

    # ---------------------------------------------------------
    # Shared HTTP client (connection pooling)
    # ---------------------------------------------------------
    @classmethod
    def get_client(cls) -> httpx.AsyncClient:
        if cls._client is None:
            cls._client = httpx.AsyncClient(
                timeout=httpx.Timeout(10.0),
                follow_redirects=True,
            )
        return cls._client

    # ---------------------------------------------------------
    # Core request method
    # ---------------------------------------------------------
    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
        data: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:

        url = f"{self.base_url}/{path.lstrip('/')}"
        client = self.get_client()
        retry_after = None
        max_retries = 4

        for attempt in range(max_retries + 1):
            self.log.info("HTTP %s %s (attempt %s)", method, url, attempt)

            try:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=self.headers,
                    params=params,
                    json=json,
                    data=data,
                )

                # Raise for non-2xx
                response.raise_for_status()

                # Parse JSON safely
                try:
                    payload = response.json()
                except ValueError:
                    self.log.error("Invalid JSON response from %s", url)
                    raise

                self.log.info("HTTP %s %s succeeded", method, url)
                return payload

            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code

                # ---------------------------------------------------------
                # Retry on 429 or 5xx
                # ---------------------------------------------------------
                if status == ErrorCode.RATE_LIMIT or ErrorCode.INTERNAL_ERROR <= status < ErrorCode.CUSTOM:
                    retry_after = exc.response.headers.get("Retry-After")

                if retry_after:
                    delay = float(retry_after)
                    self.log.warning(
                        "Rate limit or server error (%s). Retrying in %ss",
                        status,
                        delay,
                    )
                else:
                    # Exponential backoff + jitter
                    base = 0.5 * (2 ** attempt)
                    delay = base * random.uniform(0.8, 1.2)
                    self.log.warning(
                        "Retrying %s %s due to %s (delay %.2fs)",
                        method,
                        url,
                        status,
                        delay,
                    )

                    await asyncio.sleep(delay)
                    continue

                # Non-retryable HTTP error
                self.log.error(
                    "HTTP error %s %s: status=%s body=%s",
                    method,
                    url,
                    status,
                    exc.response.text,
                )
                raise

            except httpx.RequestError as exc:
                # Network issues → retry
                base = 0.5 * (2 ** attempt)
                delay = base * random.uniform(0.8, 1.2)
                self.log.warning(
                    "Network error during %s %s: %s (retrying in %.2fs)",
                    method,
                    url,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
                continue

            except Exception as exc:
                self.log.error("HTTP request failed %s %s: %s", method, url, exc)
                raise

    # ---------------------------------------------------------
    # Retries exhausted
    # ---------------------------------------------------------
        self.log.error("Max retries exceeded for %s %s", method, url)
        raise httpx.RequestError(f"Request failed after {max_retries} retries")

    # ---------------------------------------------------------
    # Convenience wrappers
    # ---------------------------------------------------------
    async def get(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self.request("GET", path, params=params)

    async def post(
        self,
        path: str,
        *,
        json: Mapping[str, Any] | None = None,
        data: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self.request("POST", path, json=json, data=data)

    async def _retry_delay(self, attempt: int) -> None:
        # Exponential backoff: 0.5, 1, 2, 4 seconds
        base = 0.5 * (2 ** attempt)
        jitter = base * random.uniform(0.8, 1.2)
        await asyncio.sleep(jitter)

