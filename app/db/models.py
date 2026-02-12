from pydantic import BaseModel

class Workspace(BaseModel):
    id: str
    slack_team_id: str
    slack_bot_token: str | None


class Integration(BaseModel):
    id: str
    workspace_id: str
    provider: str
    access_token: str
    refresh_token: str | None
    portal_id: str | None
    updated_at: str
