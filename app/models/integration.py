# app/models/integration.py
from pydantic import BaseModel
from typing import Optional

class Integration(BaseModel):
    provider: str  # "hubspot" | "slack"
    team_id: str
    access_token: str
    refresh_token: Optional[str] = None
    portal_id: Optional[str] = None
    expires_at: Optional[int] = None
    updated_at: Optional[str] = None