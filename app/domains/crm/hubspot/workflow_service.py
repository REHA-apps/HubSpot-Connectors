from __future__ import annotations

from app.core.logging import CorrelationAdapter, get_logger
from app.db.records import Provider
from app.db.storage_service import StorageService

logger = get_logger("hubspot.workflow.service")


class WorkflowService:
    """Description:
    Service for programmatically managing HubSpot Workflows via V4 Flows API.
    """

    def __init__(self, corr_id: str, storage: StorageService):
        self.corr_id = corr_id
        self.log = CorrelationAdapter(logger, corr_id)
        self.storage = storage

    async def seed_all_workflows(self, workspace_id: str) -> bool:
        """Description:
        Creates a suite of default "Getting Started" workflows in HubSpot.
        """
        integration = await self.storage.get_integration(workspace_id, Provider.HUBSPOT)
        if not integration or not integration.credentials.get("access_token"):
            self.log.error("Missing HubSpot integration for workspace=%s", workspace_id)
            return False

        token = integration.credentials["access_token"]
        portal_id = integration.metadata.get("portal_id")

        # Define default workflows
        workflows = [
            {
                "name": "Notify Slack on High-Value Lead",
                "type": "CONTACT_FLOW",
                "flowType": "WORKFLOW",
                "isEnabled": True,
                "startActionId": "notify_slack_high_value_lead",
                "actions": [
                    {
                        "type": "SINGLE_CONNECTION",
                        "actionId": "notify_slack_high_value_lead",
                        "actionTypeId": "HubSpotCRMConnectors_send_slack_message",
                        "fields": {
                            "channel_id": "general",
                            "message_text": (
                                "*High-Value Lead!* \n "
                                "*Name*: {{contact.firstname}} {{contact.lastname}}\n "
                                "*Email*: {{contact.email}}"
                            ),
                        },
                        "actionConnection": {
                            "type": "SINGLE_CONNECTION",
                            "nextActionId": None,
                        },
                    }
                ],
                "enrollmentSettings": {
                    "enrollmentTrigger": {
                        "type": "PROPERTY_CHANGE",
                        "propertyName": "hs_analytics_num_page_views",
                        "operator": "GREATER_THAN",
                        "value": "10",
                    }
                },
            },
            {
                "name": "Notify Slack on High-Priority Ticket",
                "type": "PLATFORM_FLOW",
                "flowType": "WORKFLOW",
                "objectTypeId": "0-5",  # Ticket
                "isEnabled": True,
                "startActionId": "notify_slack_high_priority_ticket",
                "actions": [
                    {
                        "type": "SINGLE_CONNECTION",
                        "actionId": "notify_slack_high_priority_ticket",
                        "actionTypeId": "HubSpotCRMConnectors_send_slack_message",
                        "fields": {
                            "channel_id": "general",
                            "message_text": (
                                "*Priority Ticket!* \n "
                                "*Subject*: {{ticket.subject}}\n "
                                "*Status*: {{ticket.hs_pipeline_stage}}\n "
                                "*Priority*: {{ticket.hs_ticket_priority}}"
                            ),
                        },
                        "actionConnection": {
                            "type": "SINGLE_CONNECTION",
                            "nextActionId": None,
                        },
                    }
                ],
                "enrollmentSettings": {
                    "enrollmentTrigger": {
                        "type": "PROPERTY_CHANGE",
                        "propertyName": "hs_ticket_priority",
                        "operator": "EQUAL",
                        "value": "High",
                    }
                },
            },
            {
                "name": "Notify Slack on New Email",
                "type": "CONTACT_FLOW",
                "flowType": "WORKFLOW",
                "isEnabled": True,
                "startActionId": "notify_slack_new_email",
                "actions": [
                    {
                        "type": "SINGLE_CONNECTION",
                        "actionId": "notify_slack_new_email",
                        "actionTypeId": "HubSpotCRMConnectors_send_slack_message",
                        "fields": {
                            "channel_id": "general",
                            "message_text": (
                                "*New Conversation Received!* \n "
                                "*From*: {{contact.firstname}} {{contact.lastname}}\n "
                                "*Email*: {{contact.email}}\n "
                                f"*Portal*: {portal_id}"
                            ),
                        },
                        "actionConnection": {
                            "type": "SINGLE_CONNECTION",
                            "nextActionId": None,
                        },
                    }
                ],
                "enrollmentSettings": {
                    "enrollmentTrigger": {
                        "type": "PROPERTY_CHANGE",
                        "propertyName": "hs_email_last_email_date",
                        "operator": "IS_KNOWN",
                    }
                },
            },
            {
                "name": "Notify Slack on New Live Chat",
                "type": "CONTACT_FLOW",
                "flowType": "WORKFLOW",
                "isEnabled": True,
                "startActionId": "notify_slack_new_live_chat",
                "actions": [
                    {
                        "type": "SINGLE_CONNECTION",
                        "actionId": "notify_slack_new_live_chat",
                        "actionTypeId": "HubSpotCRMConnectors_send_slack_message",
                        "fields": {
                            "channel_id": "general",
                            "message_text": (
                                "*New SMS Message!* \n "
                                "*From*: {{contact.firstname}} {{contact.lastname}}\n "
                                "*Text*: {{contact.hs_last_message_received_body}}"
                            ),
                        },
                        "actionConnection": {
                            "type": "SINGLE_CONNECTION",
                            "nextActionId": None,
                        },
                    }
                ],
                "enrollmentSettings": {
                    "enrollmentTrigger": {
                        "type": "PROPERTY_CHANGE",
                        "propertyName": "hs_last_message_received_body",
                        "operator": "IS_KNOWN",
                    }
                },
            },
        ]

        url = "https://api.hubapi.com/automation/v4/flows"
        headers = {"Authorization": f"Bearer {token}"}

        # Use the shared httpx.AsyncClient singleton for connection reuse
        from app.core.base_client import BaseClient

        client = BaseClient.get_client()

        async def _seed_one(payload: dict) -> bool:
            """Seed a single workflow, returning True on success."""
            try:
                response = await client.post(url, json=payload, headers=headers)
                if response.status_code == 201:  # noqa: PLR2004
                    self.log.info(
                        "Successfully seeded workflow '%s' for workspace=%s",
                        payload["name"],
                        workspace_id,
                    )
                    return True
                self.log.error(
                    "Failed to seed workflow '%s' (status=%s): %s",
                    payload["name"],
                    response.status_code,
                    response.text,
                )
                return False
            except Exception as exc:
                self.log.error("Error seeding workflow '%s': %s", payload["name"], exc)
                return False

        # Fire all workflow seeds concurrently
        import asyncio

        results = await asyncio.gather(*[_seed_one(p) for p in workflows])
        return all(results)
