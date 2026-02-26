from __future__ import annotations

import httpx

from app.core.logging import CorrelationAdapter, corr_id_ctx, get_logger

logger = get_logger("utils.http")


def normalize_object_type(object_type: str) -> str:
    """Description:
        Centralized normalization for HubSpot object types.
        Converts to lowercase, handles pluralization (e.g., 'contacts' ->
        'contact'), and maps internal numerical type IDs (e.g., '0-1' -> 'contact').

    Args:
        object_type (str): The raw object type string.

    Returns:
        str: Normalized singular object type.

    """
    # Map internal HubSpot type IDs used by UI extensions
    type_map = {
        "0-1": "contact",
        "0-2": "company",
        "0-3": "deal",
        "0-4": "ticket",
    }

    object_type = type_map.get(object_type, object_type)
    return object_type.lower().replace("ies", "y").rstrip("s")


class HTTPClient:
    """Description:
        Global asynchronous HTTP client wrapper with centralized configuration.

    Rules Applied:
        - Implements request-scoped correlation ID tracking via ContextVars.
        - Provides global logging hooks for request and response traceability.
        - Managed as a singleton AsyncClient for optimal connection pooling.
    """

    _client: httpx.AsyncClient | None = None

    @classmethod
    def get_client(cls, *, corr_id: str | None = None) -> httpx.AsyncClient:
        """Description:
            Retrieves or initializes the shared httpx.AsyncClient singleton.

        Args:
            corr_id (str | None): Optional correlation ID for the current request
                                  context.

        Returns:
            httpx.AsyncClient: The static HTTP client instance.

        Rules Applied:
            - Automatically sets the correlation ID in corr_id_ctx context.
            - Configures default timeout and logging hooks on initialization.

        """
        # Set context for hooks
        if corr_id:
            corr_id_ctx.set(corr_id)

        log = CorrelationAdapter(logger, corr_id or "no-corr-id")

        if cls._client is None or cls._client.is_closed:
            log.info("Creating new shared AsyncClient instance")

            cls._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                event_hooks={
                    "request": [cls._log_request(), cls._inject_headers()],
                    "response": [cls._log_response()],
                },
            )
        else:
            log.debug("Reusing existing shared AsyncClient instance")

        return cls._client

    # ---------------------------------------------------------
    # Logging hooks (use corr_id_ctx from app.core.logging)
    # ---------------------------------------------------------
    @staticmethod
    def _inject_headers():
        async def hook(request: httpx.Request):
            corr_id = corr_id_ctx.get("no-corr-id")
            if corr_id != "no-corr-id":
                request.headers["X-Correlation-ID"] = corr_id

        return hook

    @staticmethod
    def _log_request():
        async def hook(request: httpx.Request):
            corr_id = corr_id_ctx.get("no-corr-id")
            log = CorrelationAdapter(logger, corr_id)
            log.info("HTTP %s %s", request.method, request.url)

        return hook

    @staticmethod
    def _log_response():
        async def hook(response: httpx.Response):
            corr_id = corr_id_ctx.get("no-corr-id")
            log = CorrelationAdapter(logger, corr_id)
            log.info(
                "HTTP %s %s → %s",
                response.request.method,
                response.request.url,
                response.status_code,
            )

        return hook

    @classmethod
    async def close(cls, *, corr_id: str | None = None) -> None:
        """Description:
            Gracefully shuts down the shared HTTP client and its connection pool.

        Args:
            corr_id (str | None): Correlation ID for shutdown logging.

        Returns:
            None

        """
        log = CorrelationAdapter(logger, corr_id or "no-corr-id")

        if cls._client and not cls._client.is_closed:
            log.info("Closing shared AsyncClient instance")
            await cls._client.aclose()
            cls._client = None
        else:
            log.debug("AsyncClient already closed or not initialized")
