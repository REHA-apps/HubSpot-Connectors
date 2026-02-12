import shlex
from typing import Mapping, Any

def parse_slack_command_text(text: str) -> dict:
    try:
        parts = shlex.split(text)
        return dict(part.split("=", 1) for part in parts if "=" in part)
    except Exception:
        return {}


def coerce_to_str_dict(data: Mapping[str, Any]) -> dict[str, str | None]:
    """
    Converts all values in a mapping to str | None.
    - None stays None
    - All other values are converted to str
    """
    return {k: str(v) if v is not None else None for k, v in data.items()}

