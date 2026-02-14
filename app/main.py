from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.api.router import api_router
from app.core.config import settings
from app.core.logging import CorrelationAdapter, get_logger
from app.utils.helpers import HTTPClient

logger = get_logger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # -----------------------------
    # Startup
    # -----------------------------
    log = CorrelationAdapter(logger, "startup")
    log.info("Application starting up — listing routes")

    for route in app.routes:
        if isinstance(route, APIRoute):
            log.info("Route registered: path=%s name=%s", route.path, route.name)

    log.info("Startup complete")
    yield

    # -----------------------------
    # Shutdown
    # -----------------------------
    log = CorrelationAdapter(logger, "shutdown")
    log.info("Shutting down — closing shared HTTP clients")

    await HTTPClient.close(corr_id="shutdown")

    log.info("Shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.include_router(api_router)


@app.get("/")
async def root() -> dict[str, str]:
    """Basic health check endpoint."""
    return {"message": f"{settings.APP_NAME} is running"}
