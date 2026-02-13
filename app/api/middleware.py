# app/api/middleware.py
from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging import CorrelationAdapter, get_logger

logger = get_logger("middleware")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # 1. Extract or generate correlation ID
        corr_id = (
            request.headers.get("X-Correlation-Id") or f"evt_{uuid.uuid4().hex[:12]}"
        )
        request.state.corr_id = corr_id

        log = CorrelationAdapter(logger, corr_id)

        # 2. Log incoming request
        log.info("Incoming request %s %s", request.method, request.url.path)

        start = time.time()

        try:
            response = await call_next(request)
        except Exception as exc:
            # 3. Log unhandled exceptions
            log.error("Unhandled exception during request: %s", exc)
            raise

        duration_ms = int((time.time() - start) * 1000)

        # 4. Log response details
        log.info(
            "Completed request %s %s -> %s (%d ms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )

        # 5. Add correlation ID to response headers
        response.headers["X-Correlation-Id"] = corr_id

        return response
