from functools import lru_cache
from datetime import datetime, timezone
from typing import Any, Dict

@lru_cache(maxsize=1024)
def to_hubspot_timestamp(dt: datetime) -> int:
    """Converts a Python datetime to a HubSpot Unix millisecond timestamp."""
    return int(dt.timestamp() * 1000)

@lru_cache(maxsize=1024)
def from_hubspot_timestamp(ms: int) -> datetime:
    """Converts a HubSpot Unix millisecond timestamp to a Python datetime."""
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)

def flatten_properties(hubspot_object: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extracts HubSpot properties into a flat dictionary.
    Useful for simplifying API responses.
    """
    properties = hubspot_object.get("properties", {})
    return {**hubspot_object, **properties} if isinstance(properties, dict) else hubspot_object
