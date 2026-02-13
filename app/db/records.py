# app/db/records.py
from __future__ import annotations

from app.db.base_record import BaseRecord


class WorkspaceRecord(BaseRecord):
    required_fields = ("id",)

    id: str
    primary_email: str | None = None
    subscription_id: str | None = None


class IntegrationRecord(BaseRecord):
    required_fields = ("id", "workspace_id", "provider")

    id: str
    workspace_id: str
    provider: str

    slack_team_id: str | None = None
    slack_bot_token: str | None = None

    portal_id: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None
