from __future__ import annotations

import shlex
from collections.abc import Iterable, Mapping
from typing import Any

from app.core.logging import CorrelationAdapter, get_logger
from app.db.protocols import SupabaseRow

logger = get_logger("utils.parsers")


# Slack command parsing
def parse_slack_command_text(
    text: str,
    *,
    corr_id: str | None = None,
) -> dict[str, str]:
    """Description:
        Parses raw Slack slash command text into key-value pairs using shell-style
        splitting.

    Args:
        text (str): The raw command text (e.g., 'email=foo@bar.com').
        corr_id (str | None): Optional correlation ID for logging.

    Returns:
        dict[str, str]: Dictionary of parsed key-value pairs.

    Rules Applied:
        - Supports quoted strings for values containing spaces.
        - Only inclusions with '=' are parsed as pairs.

    """
    log = CorrelationAdapter(logger, corr_id or "no-corr-id")

    try:
        parts = shlex.split(text)
        parsed = {
            key: value for key, value in (p.split("=", 1) for p in parts if "=" in p)
        }
        log.debug("Parsed Slack command text: %s", parsed)
        return parsed

    except Exception as exc:
        log.error("Failed to parse Slack command text: %s", exc)
        return {}


# Type coercion helpers
def coerce_to_str_dict(
    data: Mapping[str, Any],
    *,
    corr_id: str | None = None,
) -> dict[str, str | None]:
    """Description:
        Normalizes a dictionary by converting all values to strings or None.

    Args:
        data (Mapping[str, Any]): The source dictionary.
        corr_id (str | None): Optional correlation ID for logging.

    Returns:
        dict[str, str | None]: A new dictionary with string-coerced values.

    """
    log = CorrelationAdapter(logger, corr_id or "no-corr-id")

    result = {
        key: (str(value) if value is not None else None) for key, value in data.items()
    }

    log.debug("Coerced mapping to str dict: %s", result)

    return result


def to_int(value) -> int | None:
    """Convert value to int, returning None on failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# Database validation helpers
def validate_supabase_row(
    data: SupabaseRow,
    required: Iterable[str],
    *,
    corr_id: str | None = None,
) -> None:
    """Description:
        Ensures that a Supabase database row contains all required fields.

    Args:
        data (SupabaseRow): The record retrieved from Supabase.
        required (Iterable[str]): List of mandatory column names.
        corr_id (str | None): Optional correlation ID for logging.

    Returns:
        None

    Rules Applied:
        - Raises ValueError if any required field is missing.

    """
    log = CorrelationAdapter(logger, corr_id or "no-corr-id")

    missing = [key for key in required if key not in data]
    if missing:
        log.error("Supabase row missing required fields: %s", missing)
        raise ValueError(f"Missing required fields: {missing}")

    log.debug("Supabase row validated successfully")
