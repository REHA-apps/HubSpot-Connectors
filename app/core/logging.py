from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from fastapi import Request

# Settings
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
USE_JSON_LOGS = os.getenv("USE_JSON_LOGS", "false").lower() == "true"
DEFAULT_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(corr_id)s - %(message)s"

# Global context for correlation IDs
corr_id_ctx: ContextVar[str] = ContextVar("corr_id", default="none")


class JsonFormatter(logging.Formatter):
    """Description:
    Custom logging formatter that outputs logs in structured JSON format.
    """

    def format(self, record: logging.LogRecord) -> str:
        corr_id = getattr(record, "corr_id", corr_id_ctx.get())

        log_data = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
            "corr_id": corr_id,
        }
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data)


@contextmanager
def log_context(corr_id: str):
    """Description:
    Context manager that sets the correlation ID for the current execution context.
    """
    token = corr_id_ctx.set(corr_id)
    try:
        yield
    finally:
        corr_id_ctx.reset(token)


class ContextFilter(logging.Filter):
    """Description:
    Logging filter that injects the current correlation ID from contextvars
    into every LogRecord.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.corr_id = corr_id_ctx.get()
        return True


def get_logger(name: str) -> logging.Logger:
    """Description:
    Configures and retrieves a named logger with context-aware correlation ID support.
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        level = os.getenv("LOG_LEVEL", "INFO").upper()
        logger.setLevel(level)

        handler = logging.StreamHandler(sys.stdout)
        handler.addFilter(ContextFilter())
        formatter = (
            JsonFormatter() if USE_JSON_LOGS else logging.Formatter(DEFAULT_FORMAT)
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        # Prevent propagation to root logger
        logger.propagate = False

    return logger


class CorrelationAdapter(logging.LoggerAdapter):
    """Logging adapter that injects a correlation ID into every log record.

    Used throughout the application for per-request traceability.
    """

    def __init__(self, logger: logging.Logger, corr_id: str, **kwargs: Any) -> None:
        self.corr_id = corr_id
        super().__init__(logger, {"corr_id": corr_id, **kwargs})

    def process(self, msg: str, kwargs: Any) -> tuple[str, Any]:
        extra = kwargs.get("extra", {})
        extra["corr_id"] = self.corr_id
        kwargs["extra"] = extra
        return msg, kwargs


async def get_corr_id(request: Request) -> str:
    """FastAPI dependency that returns the current correlation ID.

    Checks the context variable first (set by LogContextMiddleware),
    then falls back to the request header, and finally generates a new UUID.
    """
    # 1. Already set by middleware for this request
    ctx_value = corr_id_ctx.get("none")
    if ctx_value != "none":
        return ctx_value

    # 2. From incoming request header
    corr_id = request.headers.get("X-Correlation-ID")
    if corr_id:
        return corr_id

    # 3. Generate new (should rarely happen — middleware runs first)
    return str(uuid.uuid4())


def get_corr_id_from_scope(scope: Mapping[str, Any]) -> str:
    """Extract the correlation ID from a raw ASGI scope.

    Used by the pure-ASGI ``LogContextMiddleware`` which does not
    have a Starlette ``Request`` object.

    """
    headers = dict(scope.get("headers", []))
    corr_id = headers.get(b"x-correlation-id")
    if corr_id:
        return corr_id.decode()
    return str(uuid.uuid4())
