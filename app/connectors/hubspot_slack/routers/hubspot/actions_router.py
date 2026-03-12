import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.dependencies import (
    get_ai_service,
    get_hubspot_service,
    get_integration_service,
    get_slack_messaging_service,
    get_workspace_id,
)
from app.core.exceptions import IntegrationNotFoundError
from app.core.logging import get_corr_id, get_logger
from app.domains.ai.service import AIService
from app.domains.crm.hubspot.service import HubSpotService
from app.domains.crm.integration_service import IntegrationService
from app.domains.messaging.base import MessagingService

router = APIRouter(prefix="/hubspot/actions", tags=["hubspot-actions"])
logger = get_logger("hubspot.actions")


@router.post("/send-ai-insights-to-slack")
async def send_ai_insights_to_slack(
    object_id: str = Query(..., alias="objectId"),
    hs_object_type: str = Query(..., alias="hs_object_type"),
    user_email: str | None = Query(None, alias="userEmail"),
    channel: str | None = None,
    workspace_id: str = Depends(get_workspace_id),
    hubspot: HubSpotService = Depends(get_hubspot_service),
    ai: AIService = Depends(get_ai_service),
    messaging_service: MessagingService = Depends(get_slack_messaging_service),
) -> dict[str, str]:
    """Analyse a HubSpot record with AI and post the insight to Slack.

    Args:
        object_id: The HubSpot CRM object ID.
        hs_object_type: The HubSpot object type (e.g., ``0-1`` for contacts).
        user_email: Optional user email to send the DM to.
        channel: Optional Slack channel override.
        workspace_id: Internal workspace ID resolved from ``portalId``.
        hubspot: HubSpot service (injected).
        ai: AI analysis service (injected).
        messaging_service: Ready-to-use Slack messaging service (injected).

    """
    try:
        # Fetch object, engagements, and associations in parallel
        obj, engagements, associated_objects = await asyncio.gather(
            hubspot.get_object(
                workspace_id=workspace_id,
                object_type=hs_object_type,
                object_id=object_id,
            ),
            hubspot.get_object_engagements(workspace_id, hs_object_type, object_id),
            hubspot.get_all_associations(workspace_id, hs_object_type, object_id),
        )
        if not obj:
            raise HTTPException(404, f"Record not found for id {object_id}")

        # Fetch owner name if it exists
        owner_name = None
        owner_id = obj.get("properties", {}).get("hubspot_owner_id")
        if owner_id:
            try:
                owners = await hubspot.get_owners(workspace_id)
                owner = next((o for o in owners if str(o["id"]) == str(owner_id)), None)
                if owner:
                    first = owner.get("firstName", "")
                    last = owner.get("lastName", "")
                    owner_name = f"{first} {last}".strip()
            except Exception:
                logger.warning("Failed to fetch owner for record %s", object_id)

        analysis = await ai.analyze_polymorphic(
            obj,
            hs_object_type,
            engagements=engagements,
            associated_objects=associated_objects,
            owner_name=owner_name,
        )

        await messaging_service.send_ai_insights(
            workspace_id=workspace_id,
            channel=channel,
            user_email=user_email,
            analysis=analysis,
        )

        return {"status": "ok"}
    except IntegrationNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Integration not found: {exc.message}. "
                "Please ensure you have authorised both HubSpot and Slack."
            ),
        )


@router.post("/ping-owner")
async def ping_owner(
    object_id: str = Query(..., alias="objectId"),
    hs_object_type: str = Query(..., alias="hs_object_type"),
    corr_id: str = Depends(get_corr_id),
    workspace_id: str = Depends(get_workspace_id),
    hubspot: HubSpotService = Depends(get_hubspot_service),
    integration_service: IntegrationService = Depends(get_integration_service),
    messaging_service: MessagingService = Depends(get_slack_messaging_service),
) -> dict[str, str]:
    """Send a Slack DM to the record's assigned HubSpot owner.

    This is a Pro-tier feature. The Pro check is enforced server-side
    using the resolved workspace_id.

    Args:
        object_id: The HubSpot CRM object ID.
        hs_object_type: The HubSpot object type (e.g., ``0-1`` for contacts).
        corr_id: Correlation ID for structured logging.
        workspace_id: Internal workspace ID resolved from ``portalId``.
        hubspot: HubSpot service (injected).
        integration_service: Integration service (injected).
        messaging_service: Ready-to-use Slack messaging service (injected).

    Raises:
        HTTPException 403: Workspace is not on the Pro plan.
        HTTPException 404: Record, owner, or Slack user not found.
        HTTPException 400: Record has no owner assigned.

    """
    try:
        # Pro plan check
        is_pro = await integration_service.is_pro_workspace(workspace_id)
        if not is_pro:
            raise HTTPException(
                403, "Ping Owner is a Pro feature. Please upgrade your plan."
            )

        # Fetch the record and owner list in parallel
        obj, owners = await asyncio.gather(
            hubspot.get_object(
                workspace_id=workspace_id,
                object_type=hs_object_type,
                object_id=object_id,
            ),
            hubspot.get_owners(workspace_id),
        )
        if not obj:
            raise HTTPException(404, f"{hs_object_type} not found")

        owner_id = obj.get("properties", {}).get("hubspot_owner_id")
        if not owner_id:
            raise HTTPException(400, "No owner assigned to this HubSpot record.")

        owner = next((o for o in owners if str(o["id"]) == str(owner_id)), None)
        if not owner or not owner.get("email"):
            raise HTTPException(404, "Owner details or email not found in HubSpot.")

        owner_email = owner["email"]
        record_url = obj.get("hs_url", "https://app.hubspot.com")
        ping_text = (
            "Hi! A team member is requesting your attention on "
            f"this record in HubSpot:\n*{hs_object_type.capitalize()}*: {record_url}"
        )

        sent = await messaging_service.send_dm(user_email=owner_email, text=ping_text)
        if not sent:
            raise HTTPException(
                404, f"Could not find a Slack user matching email: {owner_email}"
            )

        return {"status": "ok", "message": f"Ping sent to {owner_email}"}

    except IntegrationNotFoundError as exc:
        raise HTTPException(404, detail=str(exc))
