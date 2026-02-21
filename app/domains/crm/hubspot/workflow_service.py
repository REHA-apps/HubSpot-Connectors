from __future__ import annotations

import httpx

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
                "isEnabled": True,
                "actions": [
                    {
                        "type": "ACTION",
                        "actionDefinitionId": "HubSpotCRMConnectors_send_slack_message",
                        "inputFields": {
                            "channel_id": "general",
                            "text": (
                                "*High-Value Lead!* \n "
                                "*Name*: {{contact.firstname}} {{contact.lastname}}\n "
                                "*Email*: {{contact.email}}"
                            ),
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
                "objectTypeId": "0-5",  # Ticket
                "isEnabled": True,
                "actions": [
                    {
                        "type": "ACTION",
                        "actionDefinitionId": "HubSpotCRMConnectors_send_slack_message",
                        "inputFields": {
                            "channel_id": "general",
                            "text": (
                                "*Priority Ticket!* \n "
                                "*Subject*: {{ticket.subject}}\n "
                                "*Status*: {{ticket.hs_pipeline_stage}}\n "
                                "*Priority*: {{ticket.hs_ticket_priority}}"
                            ),
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
                "isEnabled": True,
                "actions": [
                    {
                        "type": "ACTION",
                        "actionDefinitionId": "HubSpotCRMConnectors_send_slack_message",
                        "inputFields": {
                            "channel_id": "general",
                            "text": (
                                "*New Conversation Received!* \n "
                                "*From*: {{contact.firstname}} {{contact.lastname}}\n "
                                "*Email*: {{contact.email}}\n "
                                f"*Portal*: {portal_id}"
                            ),
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
                "isEnabled": True,
                "actions": [
                    {
                        "type": "ACTION",
                        "actionDefinitionId": "HubSpotCRMConnectors_send_slack_message",
                        "inputFields": {
                            "channel_id": "general",
                            "text": (
                                "*New SMS Message!* \n "
                                "*From*: {{contact.firstname}} {{contact.lastname}}\n "
                                "*Text*: {{contact.hs_last_message_received_body}}"
                            ),
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

        success = True
        async with httpx.AsyncClient() as client:
            for payload in workflows:
                try:
                    response = await client.post(
                        "https://api.hubapi.com/automation/v4/flows",
                        json=payload,
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    if response.status_code == 201:  # noqa: PLR2004
                        self.log.info(
                            "Successfully seeded workflow '%s' for workspace=%s",
                            payload["name"],
                            workspace_id,
                        )
                    else:
                        self.log.error(
                            "Failed to seed workflow '%s': %s %s",
                            payload["name"],
                            response.status_code,
                            response.text,
                        )
                        success = False
                except Exception as exc:
                    self.log.error(
                        "Error seeding workflow '%s': %s", payload["name"], exc
                    )
                    success = False

        return success
