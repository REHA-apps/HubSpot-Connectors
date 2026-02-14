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

    id: str
    email: str | None = None
    name: str | None = None
    source: str = "unknown"

    @field_validator("id")
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
    channel: str | None = None
    text: str | None = None
    blocks: list[dict[str, Any]] | None = None
    attachments: list[dict[str, Any]] | None = None
    identity: Identity | None = None

    @field_validator("channel")
    def validate_channel(cls, v):
        if v is None:
            return v
        if not isinstance(v, str):
            raise ValueError("channel must be a string")
        if not (v.startswith("C") or v.startswith("G") or v.startswith("D")):
            raise ValueError(
                f"Invalid Slack channel ID: {v}. "
                "Expected a Slack channel ID (C..., G..., or D...)."
            )
        return v
