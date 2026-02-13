# app/main.py
from __future__ import annotations

from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.api.router import api_router
from app.core.config import settings
from app.core.logging import CorrelationAdapter, get_logger

logger = get_logger("app.main")

app = FastAPI(title=settings.APP_NAME)
app.include_router(api_router)


@app.get("/")
async def root() -> dict[str, str]:
    """Basic health check endpoint."""
    return {"message": f"{settings.APP_NAME} is running"}


@app.on_event("startup")
async def startup_event() -> None:
    """Log all registered API routes on startup."""
    log = CorrelationAdapter(logger, "startup")

    log.info("Application starting up — listing routes")

    for route in api_router.routes:
        if isinstance(route, APIRoute):
            log.info("Route registered: path=%s name=%s", route.path, route.name)

    log.info("Startup complete")
