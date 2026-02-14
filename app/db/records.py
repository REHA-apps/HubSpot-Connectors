# app/db/records.py
from __future__ import annotations

from typing import ClassVar

from pydantic import SecretStr

from app.db.base_record import BaseRecord


class WorkspaceRecord(BaseRecord):
    """Represents a workspace in your system.
    Typically corresponds to a company or Slack workspace.
    """

    required_fields: ClassVar[set[str]] = {"id"}

    id: str
    primary_email: str | None = None
    subscription_id: str | None = None

    # Optional metadata
    created_at: str | None = None
    updated_at: str | None = None


class IntegrationRecord(BaseRecord):
    """Represents a single integration installation.
    One workspace may have multiple integrations:
    - Slack
    - HubSpot
    - WhatsApp (future)
    - Gmail (future)
    """

    required_fields: ClassVar[set[str]] = {"id", "workspace_id", "provider"}

    id: str
    workspace_id: str
    provider: str  # consider replacing with Enum

    # Slack fields
    slack_team_id: str | None = None
    slack_bot_token: SecretStr | None = None

    # HubSpot fields
    portal_id: str | None = None
    access_token: SecretStr | None = None
    refresh_token: SecretStr | None = None

    # Optional metadata
    created_at: str | None = None
    updated_at: str | None = None
