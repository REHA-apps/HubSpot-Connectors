# app/core/logging.py
from __future__ import annotations

import logging
import os
import time
from collections.abc import MutableMapping
from typing import Any

LOGGER_NAME = "app"

# ---------------------------------------------------------
# Shared formatter (UTC timestamps, structured-ish)
# ---------------------------------------------------------
DEFAULT_FORMAT = (
    "%(asctime)sZ | %(levelname)s | %(name)s | corr=%(corr_id)s | %(message)s"
)

logging.Formatter.converter = time.gmtime  # force UTC timestamps


def get_logger(name: str | None = None) -> logging.Logger:
    """Create or retrieve a namespaced logger with correlation-ID support.
    Ensures handlers are added only once.
    """
    logger_name = f"{LOGGER_NAME}.{name}" if name else LOGGER_NAME
    logger = logging.getLogger(logger_name)

    if not logger.handlers:
        # Log level from environment (DEV=DEBUG, PROD=INFO)
        level = os.getenv("LOG_LEVEL", "INFO").upper()
        logger.setLevel(level)

        handler = logging.StreamHandler()
        formatter = logging.Formatter(DEFAULT_FORMAT)
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


class CorrelationAdapter(logging.LoggerAdapter):
    """Logger adapter that injects correlation IDs into every log entry."""

    extra: dict[str, Any]

    def __init__(self, logger: logging.Logger, corr_id: str) -> None:
        super().__init__(logger, {"corr_id": corr_id})

    def process(
        self,
        msg: str,
        kwargs: MutableMapping[str, Any],
    ) -> tuple[str, MutableMapping[str, Any]]:
        extra = kwargs.get("extra") or {}
        extra.setdefault("corr_id", self.extra["corr_id"])
        kwargs["extra"] = extra
        return msg, kwargs


# ---------------------------------------------------------
# Optional helper for exception logging
# ---------------------------------------------------------
def log_exception(logger: logging.Logger, corr_id: str, exc: Exception) -> None:
    """Log an exception with correlation ID, without leaking stack traces
    unless LOG_LEVEL=DEBUG.
    """
    adapter = CorrelationAdapter(logger, corr_id)
    adapter.error("Exception occurred: %s", exc)
