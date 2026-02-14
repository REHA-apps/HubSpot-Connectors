# app/utils/transformers.py
from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from app.core.logging import CorrelationAdapter, get_logger

logger = get_logger("utils.transformers")


# ---------------------------------------------------------
# HubSpot timestamp conversions
# ---------------------------------------------------------
@lru_cache(maxsize=1024)
def _cached_to_hubspot_timestamp(dt: datetime) -> int:
    """Pure cached conversion without logging."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp() * 1000)


def to_hubspot_timestamp(
    dt: datetime,
    *,
    corr_id: str | None = None,
) -> int:
    """Convert datetime to HubSpot Unix ms timestamp.
    Logging is outside the cached function to avoid cache/log mismatch.
    """
    log = CorrelationAdapter(logger, corr_id or "no-corr-id")

    if dt.tzinfo is None:
        log.warning("Datetime missing timezone; assuming UTC")

    ts = _cached_to_hubspot_timestamp(dt)
    log.debug("Converted datetime to HubSpot timestamp: %s -> %s", dt, ts)
    return ts


@lru_cache(maxsize=1024)
def _cached_from_hubspot_timestamp(ms: int) -> datetime:
    """Pure cached conversion without logging."""
    return datetime.fromtimestamp(ms / 1000.0, tz=UTC)


def from_hubspot_timestamp(
    ms: int,
    *,
    corr_id: str | None = None,
) -> datetime:
    """Convert HubSpot Unix ms timestamp to datetime.
    Logging is outside the cached function to avoid cache/log mismatch.
    """
    log = CorrelationAdapter(logger, corr_id or "no-corr-id")

    dt = _cached_from_hubspot_timestamp(ms)
    log.debug("Converted HubSpot timestamp to datetime: %s -> %s", ms, dt)
    return dt


# ---------------------------------------------------------
# HubSpot object flattening
# ---------------------------------------------------------
def flatten_properties(
    hubspot_object: Mapping[str, Any],
    *,
    corr_id: str | None = None,
) -> dict[str, Any]:
    """Flatten HubSpot object properties into top-level dict.

    Example:
        {"id": "123", "properties": {"firstname": "John"}}
        → {"id": "123", "firstname": "John"}

    """
    log = CorrelationAdapter(logger, corr_id or "no-corr-id")

    props = hubspot_object.get("properties", {})
    if not isinstance(props, Mapping):
        log.warning("HubSpot object properties is not a mapping; returning original")
        return dict(hubspot_object)

    # Avoid overwriting top-level keys silently
    flattened = dict(hubspot_object)
    for key, value in props.items():
        if key in flattened:
            log.debug("Property %s overwrites top-level key", key)
        flattened[key] = value

    log.debug("Flattened HubSpot object: %s", flattened)
    return flattened
