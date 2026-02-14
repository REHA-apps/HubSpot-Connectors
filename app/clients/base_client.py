# app/clients/base_client.py
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from app.core.logging import CorrelationAdapter, get_logger

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

        self.log.info("HTTP %s %s", method, url)

        client = self.get_client()

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
            self.log.error(
                "HTTP error %s %s: status=%s body=%s",
                method,
                url,
                exc.response.status_code,
                exc.response.text,
            )
            raise

        except httpx.RequestError as exc:
            self.log.error(
                "Network error during %s %s: %s",
                method,
                url,
                exc,
            )
            raise

        except Exception as exc:
            self.log.error("HTTP request failed %s %s: %s", method, url, exc)
            raise

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
