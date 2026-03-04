"""Pure ASGI middleware for correlation-ID propagation.

Replaces BaseHTTPMiddleware to avoid the performance penalty of wrapping
every request body in a ``StreamingResponse``.
"""

from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import get_corr_id_from_scope, log_context


class LogContextMiddleware:
    """Bind a correlation ID to the logging context for each request.

    This is a pure ASGI middleware (no ``BaseHTTPMiddleware`` overhead).

    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        corr_id = get_corr_id_from_scope(scope)

        async def send_with_corr_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-correlation-id", corr_id.encode()))
                message["headers"] = headers
            await send(message)

        with log_context(corr_id):
            await self.app(scope, receive, send_with_corr_id)
