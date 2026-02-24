from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from app.core.logging import CorrelationAdapter, get_logger

logger = get_logger("utils.transformers")


# HubSpot timestamp conversions
@lru_cache(maxsize=1024)
def _cached_to_hubspot_timestamp(dt: datetime) -> int:
    """Pure cached conversion — expects UTC-aware datetime."""
    return int(dt.timestamp() * 1000)


def to_hubspot_iso8601(dt: datetime) -> str:
    """Description:
        Formats a Python datetime as a HubSpot-compatible ISO 8601 string (UTC).
        HubSpot expects millisecond precision: YYYY-MM-DDTHH:MM:SS.mmmZ

    Args:
        dt (datetime): The datetime to format.

    Returns:
        str: ISO 8601 formatted string in UTC.

    """
    if dt.tzinfo is None:
        # Naive datetime: assume UTC for simplicity or treat as local?
        # Standardize to UTC for HubSpot.
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)

    # Format: 2019-10-30T03:30:17.883Z
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def to_hubspot_timestamp(
    dt: datetime,
    *,
    corr_id: str | None = None,
) -> int:
    """Description:
        Converts a Python datetime object to a HubSpot-compatible Unix millisecond
        timestamp.

    Args:
        dt (datetime): The datetime to convert.
        corr_id (str | None): Optional correlation ID for logging.

    Returns:
        int: The resulting millisecond timestamp.

    Rules Applied:
        - Ensures UTC timezone conversion if missing.
        - Utilizes internal LRU caching for performance.

    """
    log = CorrelationAdapter(logger, corr_id or "no-corr-id")

    if dt.tzinfo is None:
        log.warning("Datetime missing timezone; assuming UTC")
        dt = dt.replace(tzinfo=UTC)

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
    """Description:
        Converts a HubSpot Unix millisecond timestamp back to a Python datetime.

    Args:
        ms (int): Target millisecond timestamp.
        corr_id (str | None): Optional correlation ID for logging.

    Returns:
        datetime: The resulting datetime object (UTC).

    Rules Applied:
        - Utilizes internal LRU caching for performance.

    """
    log = CorrelationAdapter(logger, corr_id or "no-corr-id")

    dt = _cached_from_hubspot_timestamp(ms)
    log.debug("Converted HubSpot timestamp to datetime: %s -> %s", ms, dt)
    return dt


# HubSpot object flattening
def flatten_properties(
    hubspot_object: Mapping[str, Any],
    *,
    corr_id: str | None = None,
) -> dict[str, Any]:
    """Description:
        Flattens HubSpot's nested 'properties' structure into a single-level
        dictionary.

    Args:
        hubspot_object (Mapping[str, Any]): Raw HubSpot object record.
        corr_id (str | None): Optional correlation ID for logging.

    Returns:
        dict[str, Any]: Flattened object dictionary.

    Rules Applied:
        - Promotes all nested properties to the top level.
        - Preserves existing top-level keys unless explicitly overwritten.

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


def to_datetime(value: Any) -> datetime:
    """Description:
        Converts a HubSpot property value (int milliseconds or ISO 8601 string)
        into a Python datetime object (UTC).

    Args:
        value (Any): The value to convert.

    Returns:
        datetime: UTC-aware datetime object. Defaults to epoch if unparsable.

    """
    if not value:
        return datetime.fromtimestamp(0, tz=UTC)

    # Handle numeric (millisecond timestamps)
    if isinstance(value, int | float):
        return datetime.fromtimestamp(float(value) / 1000.0, tz=UTC)

    if isinstance(value, str):
        # Handle numeric strings
        if value.replace(".", "", 1).isdigit():
            return datetime.fromtimestamp(float(value) / 1000.0, tz=UTC)

        # Handle ISO 8601 strings
        try:
            # datetime.fromisoformat handles 'Z' in 3.11+
            # Replacing Z for backwards safety if needed, though we're on 3.12
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC)
        except ValueError:
            return datetime.fromtimestamp(0, tz=UTC)

    return datetime.fromtimestamp(0, tz=UTC)
