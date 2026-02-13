from __future__ import annotations

from pydantic import BaseModel, Field


class SendMessageSchema(BaseModel):
    """Schema for sending a Slack message through your SlackConnector."""

    channel: str
    text: str


class SlackSearchResponse(BaseModel):
    """Model for passing HubSpot-enriched contact data to Slack UI blocks.

    Attributes:
        contact_name: Full name of the contact.
        contact_email: Email address of the contact.
        current_status: Lifecycle stage or CRM status.
        last_contacted: Human-readable last contact date (defaults to "Never").
        ai_summary: AI-generated summary of the contact.

    """

    contact_name: str
    contact_email: str
    current_status: str
    last_contacted: str | None = Field(default="Never")
    ai_summary: str
