# app/api/hubspot/schemas.py
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class HubSpotContactProperties(BaseModel):
    """Represents the properties of a HubSpot contact."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    email: EmailStr | None = None
    firstname: str | None = None
    lastname: str | None = None
    phone: str | None = None
    company: str | None = None
    lifecyclestage: str | None = "subscriber"

    lead_score_ai: int | None = Field(
        default=None,
        alias="hs_analytics_num_visits",
    )

    @classmethod
    def from_hubspot(cls, props: Mapping[str, Any]) -> HubSpotContactProperties:
        """Create typed properties from raw HubSpot properties dict."""
        return cls.model_validate(props)


class HubSpotContact(BaseModel):
    """Wrapper for HubSpot contact API responses."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: str | None = None
    properties: HubSpotContactProperties

    created_at: datetime | None = Field(default=None, alias="createdAt")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")

    archived: bool = False

    @classmethod
    def from_hubspot(cls, data: Mapping[str, Any]) -> HubSpotContact:
        """Normalize HubSpot contact payload into a typed model."""
        props = data.get("properties", {})
        return cls(
            id=str(data.get("id")),
            properties=HubSpotContactProperties.from_hubspot(props),
            createdAt=data.get("createdAt"),
            updatedAt=data.get("updatedAt"),
            archived=data.get("archived", False),
        )


class HubSpotTaskProperties(BaseModel):
    """Represents the fields required to create a HubSpot CRM Task."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    hs_task_subject: str
    hs_task_body: str

    hs_task_status: Literal["WAITING", "COMPLETED", "IN_PROGRESS"] = "WAITING"
    hs_task_priority: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"

    hs_timestamp: datetime
    hubspot_owner_id: str | None = None

    @classmethod
    def from_hubspot(cls, props: Mapping[str, Any]) -> HubSpotTaskProperties:
        return cls.model_validate(props)


class HubSpotTaskCreate(BaseModel):
    """Wrapper for HubSpot task creation payloads."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    properties: HubSpotTaskProperties

    @classmethod
    def from_hubspot(cls, data: Mapping[str, Any]) -> HubSpotTaskCreate:
        return cls(
            properties=HubSpotTaskProperties.from_hubspot(data.get("properties", {}))
        )
