# app/services/contact_search_service.py
from __future__ import annotations

from app.clients.hubspot_client import HubSpotClient
from app.clients.slack_client import SlackClient
from app.connectors.slack_connector import SlackConnector
from app.core.logging import get_logger
from app.db.supabase import StorageService
from app.integrations.ai_service import AIService
from app.integrations.slack_ui import build_card

logger = get_logger("contact_search")


async def hubspot_contact_search(
    team_id: str,
    query: str,
    response_url: str,
    corr_id: str,
) -> None:
    storage = StorageService(corr_id=corr_id)

    # ------------------------------------------------------------
    # 1. Resolve Slack integration
    # ------------------------------------------------------------
    slack_integration = storage.get_integration_by_slack_team_id(team_id)
    if not slack_integration:
        logger.error("No Slack integration found for team_id=%s", team_id)
        return

    if not slack_integration.slack_bot_token:
        logger.error("Slack bot token missing for team_id=%s", team_id)
        return

    slack_client = SlackClient(token=slack_integration.slack_bot_token)
    slack = SlackConnector(client=slack_client, corr_id=corr_id)

    # ------------------------------------------------------------
    # 2. Resolve HubSpot integration
    # ------------------------------------------------------------
    hubspot_integration = storage.get_integration_by_workspace_and_provider(
        workspace_id=slack_integration.workspace_id,
        provider="hubspot",
    )

    if not hubspot_integration:
        await slack.client.send_message(
            channel=response_url,
            text="❌ HubSpot is not connected for this workspace.",
        )
        return

    if not hubspot_integration.access_token:
        await slack.client.send_message(
            channel=response_url,
            text="❌ HubSpot access token missing. Please reconnect HubSpot.",
        )
        return

    hubspot = HubSpotClient(
        access_token=hubspot_integration.access_token,
        refresh_token=hubspot_integration.refresh_token,
        workspace_id=hubspot_integration.workspace_id,
        corr_id=corr_id,
    )

    # ------------------------------------------------------------
    # 3. Search HubSpot
    # ------------------------------------------------------------
    contacts = await hubspot.search_contacts(query)
    leads = await hubspot.search_leads(query)
    deals = await hubspot.search_deals(query)

    all_objects = contacts + leads + deals

    if not all_objects:
        await slack.client.send_message(
            channel=response_url,
            text=f"❌ No HubSpot records found for *{query}*.",
        )
        return

    # ------------------------------------------------------------
    # 4. AI summary
    # ------------------------------------------------------------
    summary = AIService.summarize_results(all_objects)
    await slack.client.send_message(
        channel=response_url,
        text=summary,
    )

    # ------------------------------------------------------------
    # 5. AI top recommended actions
    # ------------------------------------------------------------
    actions = AIService.top_recommended_actions(all_objects)
    if actions:
        formatted = "\n".join(f"• {a}" for a in actions)
        await slack.client.send_message(
            channel=response_url,
            text=f"🧠 *Top Recommended Actions:*\n{formatted}",
        )

    # ------------------------------------------------------------
    # 6. Render each card
    # ------------------------------------------------------------
    for obj in all_objects:
        ai_summary = AIService.generate_contact_insight(obj)
        card = build_card(obj, ai_summary)

        await slack.client.send_message(
            channel=response_url,
            text=f"Results for {query}",
            blocks=card["blocks"],
        )
