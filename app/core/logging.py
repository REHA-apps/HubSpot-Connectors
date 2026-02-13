# app/core/logging.py
from __future__ import annotations

import logging
from collections.abc import MutableMapping
from typing import Any

LOGGER_NAME = "app"


def get_logger(name: str | None = None) -> logging.Logger:
    """Create or retrieve a namespaced logger with correlation-ID support.
    Ensures handlers are added only once.
    """
    logger_name = f"{LOGGER_NAME}.{name}" if name else LOGGER_NAME
    logger = logging.getLogger(logger_name)

    if not logger.handlers:
        logger.setLevel(logging.INFO)

        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | corr=%(corr_id)s | %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


class CorrelationAdapter(logging.LoggerAdapter):
    extra: dict[str, Any]  # override LoggerAdapter's loose typing

    def __init__(self, logger: logging.Logger, corr_id: str) -> None:
        self.extra = {"corr_id": corr_id}
        super().__init__(logger, self.extra)

    def process(
        self,
        msg: str,
        kwargs: MutableMapping[str, Any],
    ) -> tuple[str, MutableMapping[str, Any]]:
        extra: dict[str, Any] = kwargs.get("extra") or {}
        extra.setdefault("corr_id", self.extra["corr_id"])
        kwargs["extra"] = extra
        return msg, kwargs
