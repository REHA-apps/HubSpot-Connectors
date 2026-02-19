from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_corr_id, log_context


class LogContextMiddleware(BaseHTTPMiddleware):
    """Description:
    Middleware that extracts or generates a correlation ID and binds it
    to the logging context for the duration of the request.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        corr_id = await get_corr_id(request)

        with log_context(corr_id):
            response = await call_next(request)
            response.headers["X-Correlation-ID"] = corr_id
            return response
