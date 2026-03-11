from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, ClassVar

from pydantic import Field

from app.db.base_record import BaseRecord


class Provider(StrEnum):
    SLACK = "slack"
    HUBSPOT = "hubspot"
    WHATSAPP = "whatsapp"
    GMAIL = "gmail"


class PlanTier(StrEnum):
    FREE = "free"
    PRO = "pro"
    TRIAL = "trial"

    @classmethod
    def from_string(cls, value: str) -> PlanTier:
        return cls(value) if value in cls.__members__ else cls.FREE


class WorkspaceRecord(BaseRecord):
    """Description:
        Persistence model representing a workspace (e.g., a company or Slack team).

    Rules Applied:
        - Requires a unique string 'id' as the primary identifier.
    """

    required_fields: ClassVar[set[str]] = {"id"}

    id: str
    primary_email: str | None = None
    portal_id: str | None = None
    subscription_id: str | None = None
    subscription_status: str | None = "inactive"  # 'active', 'inactive', 'trialing'
    stripe_customer_id: str | None = None
    plan: PlanTier = PlanTier.FREE
    trial_ends_at: datetime | None = None
    install_date: datetime | None = None

    # Optional metadata
    created_at: datetime | None = None
    updated_at: datetime | None = None


class IntegrationRecord(BaseRecord):
    """Description:
        Unified persistence model for all integration installations (Slack, HubSpot).

    Rules Applied:
        - Utilizes generic JSONB 'credentials' and 'metadata' fields for flexibility.
        - Links a provider integration to a specific workspace ID.
    """

    required_fields: ClassVar[set[str]] = {"id", "workspace_id", "provider"}

    id: str
    workspace_id: str
    provider: Provider

    # Flexible storage for all platforms
    # Supabase jsonb columns
    credentials: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Optional metadata
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # Convenience helpers
    def is_slack(self) -> bool:
        return self.provider == Provider.SLACK

    def is_hubspot(self) -> bool:
        return self.provider == Provider.HUBSPOT

    # Credential access helpers
    @property
    def access_token(self) -> str | None:
        return self.credentials.get("access_token")

    @property
    def refresh_token(self) -> str | None:
        return self.credentials.get("refresh_token")

    @property
    def expires_at(self) -> int | None:
        return self.credentials.get("expires_at")

    @property
    def slack_bot_token(self) -> str | None:
        return self.credentials.get("access_token") or self.credentials.get(
            "slack_bot_token"
        )

    @property
    def portal_id(self) -> str | None:
        return self.metadata.get("portal_id")

    @property
    def slack_team_id(self) -> str | None:
        return self.metadata.get("slack_team_id")

    @property
    def channel_id(self) -> str | None:
        return self.metadata.get("channel_id")


class ThreadMappingRecord(BaseRecord):
    """Description:
    Maps a CRM object to its corresponding Slack thread.
    """

    required_fields: ClassVar[set[str]] = {
        "workspace_id",
        "object_type",
        "object_id",
        "channel_id",
        "thread_ts",
    }

    workspace_id: str
    object_type: str
    object_id: str
    channel_id: str
    thread_ts: str


class ScoringConfigRecord(BaseRecord):
    required_fields: ClassVar[set[str]] = {"workspace_id"}

    workspace_id: str

    visit_threshold_moderate: int = 5
    visit_threshold_high: int = 10
    visit_threshold_very_high: int = 15

    weight_high_visit: int = 30
    weight_moderate_visit: int = 15
    weight_qualified_lifecycle: int = 25
    weight_has_company: int = 10
    weight_has_email: int = 10
    weight_recency_bonus_high: int = 15
    weight_recency_bonus_medium: int = 8
    weight_recency_bonus_low: int = 3
    weight_velocity_bonus: int = 15
    weight_stage_stale_penalty: int = -15

    max_score: int = 100

    created_at: datetime | None = None
    updated_at: datetime | None = None


class AIScoreRecord(BaseRecord):
    required_fields: ClassVar[set[str]] = {
        "workspace_id",
        "object_type",
        "object_id",
    }

    workspace_id: str
    object_type: str
    object_id: str

    score: int
    score_reason: str
    next_action: str

    updated_at: datetime | None = None
