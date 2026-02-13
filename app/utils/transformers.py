# app/utils/transformers.py
from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from app.core.logging import CorrelationAdapter, get_logger

logger = get_logger("utils.transformers")


@lru_cache(maxsize=1024)
def to_hubspot_timestamp(
    dt: datetime,
    *,
    corr_id: str | None = None,
) -> int:
    """Convert datetime to HubSpot Unix ms timestamp."""
    log = CorrelationAdapter(logger, corr_id or "no-corr-id")

    if dt.tzinfo is None:
        log.warning("Datetime missing timezone; assuming UTC")
        dt = dt.replace(tzinfo=UTC)

    ts = int(dt.timestamp() * 1000)
    log.debug("Converted datetime to HubSpot timestamp: %s -> %s", dt, ts)
    return ts


@lru_cache(maxsize=1024)
def from_hubspot_timestamp(
    ms: int,
    *,
    corr_id: str | None = None,
) -> datetime:
    """Convert HubSpot Unix ms timestamp to datetime."""
    log = CorrelationAdapter(logger, corr_id or "no-corr-id")

    dt = datetime.fromtimestamp(ms / 1000.0, tz=UTC)
    log.debug("Converted HubSpot timestamp to datetime: %s -> %s", ms, dt)
    return dt


def flatten_properties(
    hubspot_object: Mapping[str, Any],
    *,
    corr_id: str | None = None,
) -> dict[str, Any]:
    """Flatten HubSpot object properties into top-level dict."""
    log = CorrelationAdapter(logger, corr_id or "no-corr-id")

    properties = hubspot_object.get("properties", {})
    if not isinstance(properties, Mapping):
        log.warning("HubSpot object properties is not a mapping; returning original")
        return dict(hubspot_object)

    flattened = {**hubspot_object, **properties}
    log.debug("Flattened HubSpot object: %s", flattened)
    return flattened
