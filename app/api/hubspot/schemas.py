# app/api/hubspot/schemas.py
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class HubSpotContactProperties(BaseModel):
    """Represents the properties of a HubSpot contact.

    This model is used both for:
    - Incoming HubSpot webhook payloads
    - Outgoing create/update contact requests
    """

    model_config = ConfigDict(populate_by_name=True)

    email: EmailStr
    firstname: str | None = None
    lastname: str | None = None
    phone: str | None = None
    company: str | None = None
    lifecyclestage: str | None = "subscriber"

    # Aliased to a real HubSpot property for demonstration
    lead_score_ai: int | None = Field(
        default=None,
        alias="hs_analytics_num_visits",
    )


class HubSpotContact(BaseModel):
    """Wrapper for HubSpot contact API responses."""

    id: str | None = None
    properties: HubSpotContactProperties

    created_at: datetime | None = Field(default=None, alias="createdAt")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")

    archived: bool = False


class HubSpotTaskProperties(BaseModel):
    """Represents the fields required to create a HubSpot CRM Task."""

    hs_task_subject: str
    hs_task_body: str

    hs_task_status: Literal["WAITING", "COMPLETED", "IN_PROGRESS"] = "WAITING"
    hs_task_priority: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"

    # HubSpot expects a timestamp (ISO or epoch ms)
    hs_timestamp: datetime

    hubspot_owner_id: str | None = None


class HubSpotTaskCreate(BaseModel):
    """Wrapper for HubSpot task creation payloads."""

    properties: HubSpotTaskProperties
