from pydantic import BaseModel
from typing import Optional

class SendMessageSchema(BaseModel):
    channel: str
    text: str


class SlackSearchResponse(BaseModel):
    """Model for passing HubSpot data to the Slack UI generator.
    
    Attributes:
        contact_name: Full name of the contact.
        contact_email: Email address.
        current_status: Current lifecycle stage or status.
        last_contacted: Human-readable last contact date.
        ai_summary: AI-generated summary of the contact.
    """
    contact_name: str
    contact_email: str
    current_status: str
    last_contacted: Optional[str] = "Never"
    ai_summary: str
