from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.api.router import api_router
from app.core.config import settings
from app.core.exceptions import AppError, IntegrationNotFoundError
from app.core.logging import get_corr_id, get_logger, log_context
from app.core.middleware import LogContextMiddleware
from app.utils.helpers import HTTPClient

logger = get_logger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Description:
        Manages the application lifecycle, including startup logging and shutdown
        cleanup.

    Args:
        app (FastAPI): The FastAPI application instance.

    Returns:
        AsyncContextManager: The lifecycle context.

    Rules Applied:
        - Logs all registered routes on startup.
        - Ensures shared HTTP clients are closed on shutdown.

    """
    with log_context("startup"):
        logger.info("Application starting up — listing routes")
        for route in app.routes:
            if isinstance(route, APIRoute):
                logger.info("Route registered: path=%s name=%s", route.path, route.name)
        logger.info("Startup complete")

    yield

    with log_context("shutdown"):
        logger.info("Shutting down — closing shared HTTP clients")
        await HTTPClient.close(corr_id="shutdown")
        logger.info("Shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(LogContextMiddleware)


@app.exception_handler(AppError)
async def app_exception_handler(request: Request, exc: AppError):
    """Handles custom domain exceptions and returns structured JSON responses."""
    corr_id = await get_corr_id(request)
    status_code = 400

    if isinstance(exc, IntegrationNotFoundError):
        status_code = 404

    with log_context(corr_id):
        logger.warning("%s: %s", exc.__class__.__name__, exc.message)

    return JSONResponse(
        status_code=status_code,
        content={
            "error": exc.__class__.__name__,
            "message": exc.message,
            "correlation_id": corr_id,
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler to capture all unhandled errors.
    Logs the error with correlation ID and returns a clean JSON response.
    """
    corr_id = await get_corr_id(request)

    with log_context(corr_id):
        logger.error("Unhandled exception: %s", exc, exc_info=True)

    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "detail": str(exc) if settings.DEBUG else "An unexpected error occurred.",
            "correlation_id": corr_id,
        },
    )


app.include_router(api_router, prefix="/api")


@app.get("/")
async def root() -> dict[str, str]:
    """Description:
        Basic health check endpoint to verify the service is running.

    Returns:
        dict[str, str]: A message containing the application name.

    """
    return {"message": f"{settings.APP_NAME} is running"}
