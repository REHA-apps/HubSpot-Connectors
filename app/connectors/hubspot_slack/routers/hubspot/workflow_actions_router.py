from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel

from app.core.dependencies import get_integration_service
from app.core.logging import get_corr_id, get_logger
from app.db.records import Provider
from app.domains.crm.integration_service import IntegrationService
from app.domains.messaging.slack.service import SlackMessagingService

logger = get_logger("hubspot.workflow-actions")
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

    message_text = payload.fields.get("message_text")
    workspace_id = payload.fields.get("workspace_id")

    if not workspace_id:
        # portal_id (e.g. 147910822) is NOT the workspace_id.
        # Resolve the real workspace_id via the HubSpot integration record.
        hs_integration = await integration_service.storage.get_integration_by_portal_id(
            portal_id
        )
        if not hs_integration:
            return {
                "status": "ok",
                "message": f"No HubSpot integration found for portal_id={portal_id}",
            }
        workspace_id = hs_integration.workspace_id

    slack_integration = await integration_service.get_integration(
        workspace_id=workspace_id,
        provider=Provider.SLACK,
    )
    if not slack_integration:
        return {"status": "ok", "message": "Slack not connected for this workspace"}

    # Resolve channel: use workflow field value first;
    # fall back to the default channel saved in the settings page.
    channel_id = payload.fields.get("channel_id") or slack_integration.metadata.get(
        "channel_id", ""
    )

    # Initialize MessagingService to handle Slack dispatch
    messaging_service = SlackMessagingService(
        corr_id=corr_id,
        integration_service=integration_service,
        slack_integration=slack_integration,
    )

    # Resolve channel name → ID if a human-readable name was given
    target_id = channel_id
    is_slack_id = (
        channel_id
        and len(channel_id) >= 9  # noqa: PLR2004
        and channel_id[0] in ("C", "G", "D", "U")
        and channel_id[1:].isalnum()
        and channel_id[1:].isupper()
    )
    if channel_id and not is_slack_id:
        slack_channel = await messaging_service.get_slack_channel()
        resolved_id = await slack_channel.resolve_channel_name(channel_id)
        if resolved_id:
            target_id = resolved_id

    # Send message to Slack
    resp = await messaging_service.send_message(
        workspace_id=workspace_id,
        channel=target_id,
        text=message_text,
    )

    # If the message was sent successfully and we have object context from HubSpot,
    # map the thread so users can reply natively in Slack.
    if resp and resp.get("ts"):
        obj_type = payload.object.get("objectType")
        obj_id = payload.object.get("objectId")
        if obj_type and obj_id:
            logger.info(
                "Storing thread mapping for workflow action obj=%s:%s",
                obj_type,
                obj_id,
            )
            await integration_service.storage.upsert_thread_mapping(
                {
                    "workspace_id": workspace_id,
                    "object_type": obj_type.lower(),
                    "object_id": str(obj_id),
                    "channel_id": target_id,
                    "thread_ts": str(resp.get("ts")),
                }
            )

    return {"status": "ok"}
