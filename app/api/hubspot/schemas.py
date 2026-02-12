from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import Optional
from datetime import datetime

class HubSpotContactProperties(BaseModel):
    """The data fields within a HubSpot Contact.
    
    Attributes:
        email: The contact's email address.
        firstname: The contact's first name.
        lastname: The contact's last name.
        phone: The contact's phone number.
        company: The contact's company name.
        lifecyclestage: The stage of the contact in the lifecycle.
        lead_score_ai: AI-calculated lead score, aliased to HubSpot's 
            analytics visit count for demonstration.
    """
    model_config = ConfigDict(populate_by_name=True)

    email: EmailStr
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    lifecyclestage: Optional[str] = "subscriber"
    # Aliasing to a real HubSpot property for demonstration
    lead_score_ai: Optional[int] = Field(default=None, alias="hs_analytics_num_visits")

class HubSpotContact(BaseModel):
    """The wrapper HubSpot uses for API responses.
    
    Attributes:
        id: Unique HubSpot object ID.
        properties: The contact properties.
        created_at: ISO timestamp of creation.
        updated_at: ISO timestamp of last update.
        archived: Whether the contact is archived.
    """
    id: Optional[str] = None
    properties: HubSpotContactProperties
    created_at: Optional[datetime] = Field(None, alias="createdAt")
    updated_at: Optional[datetime] = Field(None, alias="updatedAt")
    archived: bool = False

class HubSpotTaskProperties(BaseModel):
    """Fields required to create a Task in the HubSpot CRM.
    
    Attributes:
        hs_task_subject: Subject line of the task.
        hs_task_body: Detailed body/description of the task.
        hs_task_status: Status (WAITING, COMPLETED, IN_PROGRESS).
        hs_task_priority: Priority level (LOW, MEDIUM, HIGH).
        hs_timestamp: Due date timestamp.
        hubspot_owner_id: ID of the HubSpot user who owns this task.
    """
    hs_task_subject: str
    hs_task_body: str
    hs_task_status: str = "WAITING"
    hs_task_priority: str = "MEDIUM"
    hs_timestamp: str
    hubspot_owner_id: Optional[str] = None

class HubSpotTaskCreate(BaseModel):
    """Payload wrapper for creating a HubSpot Task."""
    properties: HubSpotTaskProperties