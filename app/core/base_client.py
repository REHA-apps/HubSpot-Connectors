from __future__ import annotations

import asyncio
import random
from collections.abc import Mapping
from typing import Any

import httpx

from app.core.logging import CorrelationAdapter, get_logger
from app.utils.constants import ErrorCode

logger = get_logger("base_client")


class BaseClient:
    """Description:
        Base asynchronous HTTP client for external service integrations.

    Rules Applied:
        - Utilizes a shared httpx.AsyncClient for connection pooling.
        - Integrates with CorrelationAdapter for request tracking.
        - Implements automatic exponential backoff for rate limits and server errors.
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

    @classmethod
    def get_client(cls) -> httpx.AsyncClient:
        """Description:
            Retrieves or initializes the shared httpx AsyncClient singleton.

        Returns:
            httpx.AsyncClient: The static HTTP client instance.

        Rules Applied:
            - Configured with a default timeout of 10.0 seconds.
            - Redirect following enabled.

        """
        if cls._client is None:
            cls._client = httpx.AsyncClient(
                timeout=httpx.Timeout(10.0),
                follow_redirects=True,
            )
        return cls._client

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
        data: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Description:
            Executes an asynchronous HTTP request with retry logic.

        Args:
            method (str): HTTP verb (GET, POST, etc.).
            path (str): API endpoint path relative to the base URL.
            params (Mapping[str, Any] | None): URL query parameters.
            json (Mapping[str, Any] | None): JSON body payload.
            data (Mapping[str, Any] | None): Form data payload.

        Returns:
            dict[str, Any]: The parsed JSON response.

        Rules Applied:
            - Performs up to 4 retries for transient failures (429, 5xx,
              Network Errors).
            - Uses exponential backoff with jitter.

        """
        if path.startswith("http"):
            url = path
        else:
            url = f"{self.base_url}/{path.lstrip('/')}"
        client = self.get_client()
        retry_after = None
        max_retries = 4

        for attempt in range(max_retries + 1):
            self.log.debug("HTTP %s %s (attempt %s)", method, url, attempt)

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

                self.log.debug("HTTP %s %s succeeded", method, url)
                return payload

            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code

                # ---------------------------------------------------------
                # Retry on 429 or 5xx
                # ---------------------------------------------------------
                is_retryable = (
                    status == ErrorCode.RATE_LIMIT
                    or ErrorCode.INTERNAL_ERROR <= status < ErrorCode.CUSTOM
                )

                if is_retryable:
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
                        base = 0.5 * (2**attempt)
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
                base = 0.5 * (2**attempt)
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

        self.log.error("Max retries exceeded for %s %s", method, url)
        raise httpx.RequestError(f"Request failed after {max_retries} retries")

    async def get(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Convenience method for GET requests."""
        return await self.request("GET", path, params=params)

    async def post(
        self,
        path: str,
        *,
        json: Mapping[str, Any] | None = None,
        data: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Convenience method for POST requests."""
        return await self.request("POST", path, json=json, data=data)
