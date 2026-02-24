from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel

from app.connectors.slack.services.channel_service import ChannelService
from app.core.dependencies import get_integration_service
from app.core.logging import get_corr_id
from app.db.records import Provider
from app.domains.crm.integration_service import IntegrationService

router = APIRouter(prefix="/integrations/hubspot", tags=["hubspot-workflow-actions"])


class HubSpotWorkflowActionPayload(BaseModel):
    callbackId: str | None = None
    origin: Mapping[str, Any]
    object: Mapping[str, Any]
    fields: Mapping[str, Any]


@router.post("/workflow-action")
async def handle_workflow_action(
    payload: HubSpotWorkflowActionPayload = Body(...),
    corr_id: str = Depends(get_corr_id),
    integration_service: IntegrationService = Depends(get_integration_service),
):
    """Handles a custom workflow action execution request from HubSpot.
    Specifically designed for the 'Send Slack Message' action.
    """
    portal_id = str(payload.origin.get("portalId"))
    channel_id = payload.fields.get("channel_id")
    message_text = payload.fields.get("message_text")

    # Resolve Slack integration for the portal
    slack_integration = await integration_service.get_integration(
        workspace_id=portal_id,
        provider=Provider.SLACK,
    )

    if not slack_integration:
        return {"status": "ok", "message": "Slack not connected for this portal"}

    # Initialize ChannelService to handle Slack dispatch
    channel_service = ChannelService(
        corr_id=corr_id,
        integration_service=integration_service,
        slack_integration=slack_integration,
    )

    # 1. Resolve channel name to ID if necessary
    target_id = channel_id

    # Check if it looks like a Slack ID (C/G/D/U + uppercase alphanumeric, length 9-12)
    is_slack_id = (
        channel_id
        and len(channel_id) >= 9  # noqa: PLR2004
        and channel_id[0] in ("C", "G", "D", "U")
        and channel_id[1:].isalnum()
        and channel_id[1:].isupper()
    )

    if channel_id and not is_slack_id:
        slack_channel = await channel_service._get_slack_channel()
        resolved_id = await slack_channel.resolve_channel_name(channel_id)
        if resolved_id:
            target_id = resolved_id

    # 2. Send message to Slack
    await channel_service.send_message(
        workspace_id=portal_id,
        channel=target_id,
        text=message_text,
    )

    return {"status": "ok"}
