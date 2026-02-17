# app/core/logging.py
from __future__ import annotations

import logging
import os
import time
import uuid
import json
from collections.abc import MutableMapping
from typing import Any
from fastapi import Request

LOGGER_NAME = "app"

# ---------------------------------------------------------
# Log formatters
# ---------------------------------------------------------
DEFAULT_FORMAT = (
    "%(asctime)sZ | %(levelname)s | %(name)s | corr=%(corr_id)s | %(message)s"
)

logging.Formatter.converter = time.gmtime  # force UTC timestamps

USE_JSON_LOGS = os.getenv("USE_JSON_LOGS", "false").lower() == "true"


class JsonFormatter(logging.Formatter):
    """Optional JSON formatter for structured logs."""

    def format(self, record: logging.LogRecord) -> str:
        data = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "logger": record.name,
            "corr_id": getattr(record, "corr_id", None),
            "message": record.getMessage(),
        }
        return json.dumps(data)


def get_logger(name: str | None = None) -> logging.Logger:
    """Create or retrieve a namespaced logger with correlation-ID support."""
    logger_name = f"{LOGGER_NAME}.{name}" if name else LOGGER_NAME
    logger = logging.getLogger(logger_name)

    if not logger.handlers:
        level = os.getenv("LOG_LEVEL", "INFO").upper()
        logger.setLevel(level)

        handler = logging.StreamHandler()
        formatter = JsonFormatter() if USE_JSON_LOGS else logging.Formatter(DEFAULT_FORMAT)
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


# ---------------------------------------------------------
# Correlation ID extraction
# ---------------------------------------------------------
def get_corr_id(request: Request) -> str:
    corr_id = request.headers.get("X-Correlation-ID")
    if corr_id:
        return corr_id

    req_id = request.headers.get("X-Request-ID")
    if req_id:
        return req_id

    return uuid.uuid4().hex


# ---------------------------------------------------------
# Logger adapter with bind() support
# ---------------------------------------------------------
class CorrelationAdapter(logging.LoggerAdapter):
    """Logger adapter that injects correlation IDs and supports context binding."""

    extra: dict[str, Any]

    def __init__(self, logger: logging.Logger, corr_id: str, **kwargs: Any) -> None:
        base = {"corr_id": corr_id}
        base.update(kwargs)
        super().__init__(logger, base)

    def bind(self, **kwargs: Any) -> "CorrelationAdapter":
        """Return a new adapter with additional context."""
        new_extra = {**self.extra, **kwargs}
        return CorrelationAdapter(self.logger, new_extra["corr_id"], **new_extra)

    def process(
        self,
        msg: str,
        kwargs: MutableMapping[str, Any],
    ) -> tuple[str, MutableMapping[str, Any]]:
        extra = kwargs.get("extra") or {}
        extra.update(self.extra)
        kwargs["extra"] = extra
        return msg, kwargs


# ---------------------------------------------------------
# Exception logging
# ---------------------------------------------------------
def log_exception(logger: logging.Logger, corr_id: str, exc: Exception, **context: Any) -> None:
    adapter = CorrelationAdapter(logger, corr_id, **context)
    adapter.error("Exception occurred: %s", exc)