from typing import Mapping, Any

from supabase import Client, create_client
from app.db.models import Integration, Workspace
from app.core.config import settings
from pydantic import BaseModel
from datetime import datetime
from app.utils.parsers import coerce_to_str_dict

JSON = dict[str, Any] | list[Any] | str | int | float | bool | None


class WorkspaceInstall(BaseModel):
    id: str | None = None
    slack_team_id: str | None = None
    slack_bot_token: str | None = None
    subscription_id: str | None = None  
    installed_at: str | None = None


class StorageService:
    """Service for handling data storage using Supabase."""

    _client: Client | None = None

    @classmethod
    def get_client(cls) -> Client:
        """Initialize or return the Supabase client."""
        if cls._client is None:
            if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
                raise ValueError("Supabase credentials missing")
            cls._client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        return cls._client

    @classmethod
    async def save_integration(
        cls, slack_team_id: str, provider: str, data: dict[str, Any]
    ) -> Integration | dict[str, Any]:
        """Upsert workspace and integration safely, returning the first
        integration or {}."""

        client = cls.get_client()

        # Step 1: Upsert Workspace
        workspace_response = (
            client.table("workspaces")
            .upsert(
                {
                    "slack_team_id": slack_team_id,
                    "slack_bot_token": data.get("slack_bot_token"),
                },
                on_conflict="slack_team_id",
            )
            .execute()
        )

        # Only keep dict items
        workspace_list: list[dict[str, Any]] = [
            item for item in (workspace_response.data or []) if isinstance(item, dict)
        ]
        if not workspace_list:
            return {}

        try:
            workspace = Workspace(**workspace_list[0])
        except Exception:
            return {}

        # Step 2: Upsert Integration
        integration_payload = {
            "workspace_id": workspace.id,
            "provider": provider,
            "access_token": data.get("access_token"),
            "refresh_token": data.get("refresh_token"),
            "portal_id": data.get("portal_id"),
            "updated_at": "now()",
        }

        response = (
            client.table("integrations")
            .upsert(integration_payload, on_conflict="workspace_id,provider")
            .execute()
        )

        integration_list: list[dict[str, Any]] = [
            item for item in (response.data or []) if isinstance(item, dict)
        ]
        if not integration_list:
            return {}

        try:
            return Integration(**integration_list[0])
        except Exception:
            return {}

    @classmethod
    async def get_by_slack_id(
        cls, slack_team_id: str, provider: str = "hubspot"
    ) -> Integration | None:
        """Get the integration for a Slack workspace safely."""
        client = cls.get_client()
        response = (
            client.table("integrations")
            .select("*, workspaces!inner(slack_team_id, slack_bot_token)")
            .eq("workspaces.slack_team_id", slack_team_id)
            .eq("provider", provider)
            .execute()
        )

        data_list: list[dict[str, Any]] = [
            item for item in (response.data or []) if isinstance(item, dict)
        ]
        if not data_list:
            return None

        try:
            return Integration(**data_list[0])
        except Exception:
            return None

    @classmethod
    async def update_tokens(
        cls,
        slack_team_id: str,
        provider: str,
        new_at: str,
        new_rt: str | None = None,
    ) -> bool:
        """Update access/refresh tokens safely."""
        try:
            workspace = await cls.get_by_slack_id(slack_team_id, provider)
            if not workspace:
                return False

            update_payload: dict[str, Any] = {
                "access_token": new_at,
                "updated_at": "now()",
            }
            if new_rt:
                update_payload["refresh_token"] = new_rt

            response = (
                cls.get_client()
                .table("integrations")
                .update(update_payload)
                .eq("id", workspace.id)
                .execute()
            )

            return bool(response.data and len(response.data) > 0)

        except Exception as e:
            print(f"❌ StorageService Update Error: {e}")
            return False
    
    @classmethod
    async def save_workspace_installation(
        cls,
        slack_team_id: str,
        slack_bot_token: str,
        subscription_id: str
    ) -> WorkspaceInstall:
        client = cls.get_client()

        # 1. Enforce one subscription = one install
        existing_sub = (
            client.table("workspaces")
            .select("*")
            .eq("subscription_id", subscription_id)
            .execute()
        )

        if existing_sub.data:
            raise ValueError("This subscription already has an installed workspace.")

        # 2. Upsert workspace
        payload = {
            "slack_team_id": slack_team_id,
            "slack_bot_token": slack_bot_token,
            "subscription_id": subscription_id,
            "installed_at": datetime.utcnow().isoformat()
        }

        response = (
            client.table("workspaces")
            .upsert(payload, on_conflict="slack_team_id")
            .execute()
        )

        # 3. Get workspace data safely
        workspace_data = response.data[0] if response.data and isinstance(response.data[0], dict) else None

        if not workspace_data:
            raise ValueError("Failed to save workspace installation.")

        # 4. Coerce all values to str | None for WorkspaceInstall
        coerced_data = {k: str(v) if v is not None else None for k, v in workspace_data.items()}

        return WorkspaceInstall(**coerced_data)

    @classmethod
    async def get_workspace_by_team_id(cls, team_id: str) -> WorkspaceInstall | None:
        client = cls.get_client()
        res = (
            client.table("workspaces")
            .select("*")
            .eq("slack_team_id", team_id)
            .limit(1)
            .execute()
        )

        # 1. Get workspace data safely
        workspace_data = res.data[0] if res.data and isinstance(res.data[0], dict) else None

        if not workspace_data:
            return None

        # 2. Coerce all values to str | None for WorkspaceInstall
        return WorkspaceInstall(**coerce_to_str_dict(workspace_data))


def get_db():
    return create_client("URL", "KEY")

