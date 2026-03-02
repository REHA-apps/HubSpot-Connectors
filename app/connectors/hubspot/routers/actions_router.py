from fastapi import APIRouter, Depends, HTTPException, Query

from app.connectors.slack.services.channel_service import ChannelService
from app.core.dependencies import (
    get_ai_service,
    get_hubspot_service,
    get_integration_service,
)
from app.core.exceptions import IntegrationNotFoundError
from app.core.logging import get_corr_id
from app.db.records import Provider
from app.domains.ai.service import AIService
from app.domains.crm.hubspot.service import HubSpotService
from app.domains.crm.integration_service import IntegrationService

router = APIRouter(prefix="/hubspot/actions", tags=["hubspot-actions"])


@router.post("/send-ai-insights-to-slack")
async def send_ai_insights_to_slack(  # noqa: PLR0913
    object_id: str = Query(..., alias="objectId"),
    portal_id: str = Query(..., alias="portalId"),
    user_email: str | None = Query(None, alias="userEmail"),
    hs_object_type: str = Query(..., alias="hs_object_type"),
    channel: str | None = None,
    corr_id: str = Depends(get_corr_id),
    hubspot: HubSpotService = Depends(get_hubspot_service),
    ai: AIService = Depends(get_ai_service),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> dict[str, str]:
    try:
        obj = await hubspot.get_object(
            workspace_id=portal_id, object_type=hs_object_type, object_id=object_id
        )
        if not obj:
            raise HTTPException(404, f"Record not found for id {object_id}")

        # 2. Extract AI Analysis
        engagements = await hubspot.get_object_engagements(
            portal_id, hs_object_type, object_id
        )
        associated_objects = await hubspot.get_all_associations(
            portal_id, hs_object_type, object_id
        )

        analysis = await ai.analyze_polymorphic(
            obj,
            hs_object_type,
            engagements=engagements,
            associated_objects=associated_objects,
        )

        hs_integration = await integration_service.get_integration(
            workspace_id=portal_id,
            provider=Provider.HUBSPOT,
        )
        if not hs_integration:
            raise IntegrationNotFoundError(f"No HubSpot found for {portal_id}")

        slack_integration = await integration_service.get_integration(
            workspace_id=hs_integration.workspace_id,
            provider=Provider.SLACK,
        )

        channel_service = ChannelService(
            corr_id=corr_id,
            integration_service=integration_service,
            slack_integration=slack_integration,
        )

        await channel_service.send_slack_ai_insights(
            workspace_id=hs_integration.workspace_id,
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
                "Please ensure you have authorized both HubSpot and Slack."
            ),
        )


@router.post("/ping-owner")
async def ping_owner(
    object_id: str = Query(..., alias="objectId"),
    portal_id: str = Query(..., alias="portalId"),
    hs_object_type: str = Query(..., alias="hs_object_type"),
    corr_id: str = Depends(get_corr_id),
    hubspot: HubSpotService = Depends(get_hubspot_service),
    integration_service: IntegrationService = Depends(get_integration_service),
):
    """Sends a Slack DM to the deal/contact owner with a link to the record."""
    try:
        # 1. Pro plan check
        is_pro = await integration_service.is_pro_workspace(portal_id)
        if not is_pro:
            raise HTTPException(
                403, "Ping Owner is a Pro feature. Please upgrade your plan."
            )

        # 2. Get the record to find the owner
        obj = await hubspot.get_object(
            workspace_id=portal_id, object_type=hs_object_type, object_id=object_id
        )
        if not obj:
            raise HTTPException(404, f"{hs_object_type} not found")

        props = obj.get("properties", {})
        owner_id = props.get("hubspot_owner_id")
        if not owner_id:
            raise HTTPException(400, "No owner assigned to this HubSpot record.")

        # 3. Resolve Owner Email
        owners = await hubspot.get_owners(portal_id)
        owner = next((o for o in owners if o["id"] == owner_id), None)
        if not owner or not owner.get("email"):
            raise HTTPException(404, "Owner details or email not found in HubSpot.")

        owner_email = owner["email"]

        # 4. Resolve Slack User ID & Send DM
        slack_integration = await integration_service.get_integration(
            workspace_id=portal_id,
            provider=Provider.SLACK,
        )
        if not slack_integration:
            raise HTTPException(404, "Slack integration not found for this workspace.")

        channel_service = ChannelService(
            corr_id=corr_id,
            integration_service=integration_service,
            slack_integration=slack_integration,
        )
        slack_channel = await channel_service.get_slack_channel()

        slack_user_id = await slack_channel.get_user_by_email(owner_email)
        if not slack_user_id:
            raise HTTPException(
                404, f"Could not find a Slack user matching email: {owner_email}"
            )

        # Build Deep Link
        record_url = obj.get("hs_url", "https://app.hubspot.com")

        ping_text = (
            "Hi! A team member is requesting your attention on "
            "this record in HubSpot:\n"
            f"*{hs_object_type.capitalize()}*: "
            f"{record_url}"
        )

        await slack_channel.send_dm(user_id=slack_user_id, text=ping_text)

        return {"status": "ok", "message": f"Ping sent to {owner_email}"}

    except IntegrationNotFoundError as exc:
        raise HTTPException(404, detail=str(exc))
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(500, detail=f"Failed to ping owner: {str(exc)}")
