from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import Optional, Dict, Any
from datetime import datetime

class HubSpotContactProperties(BaseModel):
    """The actual data fields within a HubSpot Contact."""
    model_config = ConfigDict(populate_by_name=True)

    email: EmailStr
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    lifecyclestage: Optional[str] = "subscriber"
    # This is where your AI/ML 'Sentiment' would be stored
    lead_score_ai: Optional[int] = Field(default=None, alias="hs_analytics_num_visits")

class HubSpotContact(BaseModel):
    """The wrapper HubSpot uses for API responses."""
    id: Optional[str] = None
    properties: HubSpotContactProperties
    created_at: Optional[datetime] = Field(None, alias="createdAt")
    updated_at: Optional[datetime] = Field(None, alias="updatedAt")
    archived: bool = False

class HubSpotTaskProperties(BaseModel):
    """Fields required to create a Task in the CRM."""
    hs_task_subject: str
    hs_task_body: str  # The AI-generated summary of the Slack thread
    hs_task_status: str = "WAITING" # WAITING, COMPLETED, IN_PROGRESS
    hs_task_priority: str = "MEDIUM" # Your AI logic will set this to HIGH if urgent
    hs_timestamp: str # When the task is due
    hubspot_owner_id: Optional[str] = None

class HubSpotTaskCreate(BaseModel):
    properties: HubSpotTaskProperties

class SlackSearchResponse(BaseModel):
    """A clean model to pass data from HubSpot to the Slack UI generator."""
    contact_name: str
    contact_email: str
    current_status: str
    last_contacted: Optional[str] = "Never"
    ai_summary: str  # A 1-sentence AI summary of why this contact matters
