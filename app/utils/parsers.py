# app/utils/parsers.py
from __future__ import annotations

import shlex
from collections.abc import Iterable, Mapping
from typing import Any

from app.core.logging import CorrelationAdapter, get_logger
from app.db.protocols import SupabaseRow

logger = get_logger("utils.parsers")


# ---------------------------------------------------------
# Slack command parsing
# ---------------------------------------------------------
def parse_slack_command_text(
    text: str,
    *,
    corr_id: str | None = None,
) -> dict[str, str]:
    """Parse Slack slash command text into key=value pairs.

    Example:
        "email=john@example.com stage=lead"
        → {"email": "john@example.com", "stage": "lead"}

    Supports quoted values:
        'name="John Doe" role=admin'

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


# ---------------------------------------------------------
# Coercion helpers
# ---------------------------------------------------------
def coerce_to_str_dict(
    data: Mapping[str, Any],
    *,
    corr_id: str | None = None,
) -> dict[str, str | None]:
    """Convert mapping values to str | None.

    Useful for normalizing HubSpot or Slack payloads before persistence.
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


# ---------------------------------------------------------
# Supabase row validation
# ---------------------------------------------------------
def validate_supabase_row(
    data: SupabaseRow,
    required: Iterable[str],
    *,
    corr_id: str | None = None,
) -> None:
    """Validate that required fields exist in a Supabase row.

    Raises ValueError if missing.
    """
    log = CorrelationAdapter(logger, corr_id or "no-corr-id")

    missing = [key for key in required if key not in data]
    if missing:
        log.error("Supabase row missing required fields: %s", missing)
        raise ValueError(f"Missing required fields: {missing}")

    log.debug("Supabase row validated successfully")
