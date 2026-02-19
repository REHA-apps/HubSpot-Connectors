from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


# ---------------------------------------------------------
# Identity
# ---------------------------------------------------------
class Identity(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
        populate_by_name=True,
    )

    external_id: str
    provider: str = "unknown"
    email: str | None = None
    name: str | None = None
    source: str = "unknown"

    @field_validator("external_id")
    def ensure_str(cls, v):
        return str(v)


# ---------------------------------------------------------
# Normalized event
# ---------------------------------------------------------
class NormalizedEvent(BaseModel):
    model_config = ConfigDict(
        frozen=False,
        extra="ignore",
        populate_by_name=True,
    )

    workspace_id: str
    source: str
    event_type: str
    identity: Identity
    payload: dict[str, Any]
    timestamp: str | None = None

    @field_validator("payload")
    def ensure_dict(cls, v):
        if not isinstance(v, dict):
            raise ValueError("payload must be a dict")
        return v


# ---------------------------------------------------------
# Outbound message
# ---------------------------------------------------------
class OutboundMessage(BaseModel):
    model_config = ConfigDict(
        frozen=False,
        extra="ignore",
        populate_by_name=True,
    )

    workspace_id: str
    destination: str | None = None
    text: str | None = None

    # Platform-agnostic bucket for rich formatting (Blocks, Templates, Threading, etc.)
    provider_metadata: dict[str, Any] = {}

    # Optional identity (for auditing or routing)
    identity: Identity | None = None

    @field_validator("destination")
    def validate_destination(cls, v):
        if v is None:
            return v
        if not isinstance(v, str):
            raise ValueError("destination must be a string")
        return v
