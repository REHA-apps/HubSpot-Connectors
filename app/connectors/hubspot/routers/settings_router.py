from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.dependencies import get_corr_id, get_storage_service
from app.core.logging import CorrelationAdapter, get_logger
from app.db.records import Provider
from app.db.storage_service import StorageService

router = APIRouter(prefix="/hubspot/settings", tags=["hubspot-settings"])
logger = get_logger("hubspot.settings")


async def _resolve_workspace_id(
    portal_id: str | int, storage: StorageService, log: CorrelationAdapter
) -> str:
    """Look up the internal workspace_id from a HubSpot portal ID.

    Uses the existing get_integration_by_portal_id method which queries the
    HubSpot integration record by its metadata portal_id field.
    """
    portal_id_str = str(portal_id)
    hs_integration = await storage.get_integration_by_portal_id(portal_id_str)
    if not hs_integration:
        log.warning("No HubSpot integration found for portal_id=%s", portal_id_str)
        raise HTTPException(
            status_code=404,
            detail=f"No HubSpot integration found for portal_id={portal_id_str}",
        )
    return hs_integration.workspace_id


class SettingsPayload(BaseModel):
    portal_id: str | int
    channel: str
    notifs_enabled: bool


@router.post("/save")
async def save_settings(
    payload: SettingsPayload,
    corr_id: str = Depends(get_corr_id),
    storage: StorageService = Depends(get_storage_service),
) -> dict:
    """Save Slack connector settings for a workspace.

    Accepts the HubSpot portal_id (available in UI Extension context) and
    resolves the internal workspace_id via the HubSpot integration record.
    Settings are stored in the Slack integration's metadata field.
    """
    log = CorrelationAdapter(logger, corr_id)
    log.info("Saving settings for portal_id=%s", payload.portal_id)

    workspace_id = await _resolve_workspace_id(payload.portal_id, storage, log)

    integration = await storage.get_integration(workspace_id, Provider.SLACK)
    if not integration:
        raise HTTPException(status_code=404, detail="Slack integration not found")

    metadata = dict(integration.metadata or {})
    metadata.update(
        {
            "channel_id": payload.channel,
            "notifications_enabled": payload.notifs_enabled,
        }
    )

    await storage.upsert_integration(
        {
            "id": integration.id,
            "workspace_id": workspace_id,
            "provider": Provider.SLACK,
            "credentials": integration.credentials,
            "metadata": metadata,
        }
    )

    log.info(
        "Settings saved: channel=%s notifs=%s", payload.channel, payload.notifs_enabled
    )
    return {"success": True}


@router.get("/load")
async def load_settings(
    portal_id: str,
    corr_id: str = Depends(get_corr_id),
    storage: StorageService = Depends(get_storage_service),
) -> dict:
    """Load Slack connector settings for a workspace.

    Accepts portal_id as a query param:
    ``GET /api/hubspot/settings/load?portal_id=<id>``
    """
    log = CorrelationAdapter(logger, corr_id)
    log.info("Loading settings for portal_id=%s", portal_id)

    workspace_id = await _resolve_workspace_id(portal_id, storage, log)

    integration = await storage.get_integration(workspace_id, Provider.SLACK)
    if not integration:
        raise HTTPException(status_code=404, detail="Slack integration not found")

    metadata = integration.metadata or {}
    return {
        "channel": metadata.get("channel_id", ""),
        "notifs_enabled": metadata.get("notifications_enabled", True),
    }
