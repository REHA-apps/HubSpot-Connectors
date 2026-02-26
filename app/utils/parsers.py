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


def to_int(value: Any) -> int | None:
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


def parse_hs_task_command(text: str) -> dict[str, Any]:
    """Description:
        Parses advanced parameters from /hs-task command text.
        Supports:
        - Mentions: <@U12345> -> extract user_id
        - Due dates: today, tomorrow, next week
        - Task name: remaining text

    Args:
        text (str): The raw command text.

    Returns:
        dict[str, Any]: Parsed components (subject, mention, due_date).

    """
    import re
    from datetime import UTC, datetime, timedelta

    result: dict[str, Any] = {
        "subject": text,
        "slack_user_id": None,
        "due_date": None,
    }

    # 1. Extract Slack Mention (@user)
    mention_match = re.search(r"<@([A-Z0-9]+)>", text)
    if mention_match:
        result["slack_user_id"] = mention_match.group(1)
        text = text.replace(mention_match.group(0), "").strip()

    # 2. Extract Relative Due Dates
    now = datetime.now(UTC)
    date_patterns = {
        r"\btoday\b": now,
        r"\btomorrow\b": now + timedelta(days=1),
        r"\bnext week\b": now + timedelta(weeks=1),
    }

    for pattern, dt in date_patterns.items():
        if re.search(pattern, text, re.IGNORECASE):
            result["due_date"] = dt
            text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
            break

    # 3. Clean up subject
    # Remove extra spaces caused by parameter extraction
    result["subject"] = re.sub(r"\s+", " ", text).strip()

    return result
