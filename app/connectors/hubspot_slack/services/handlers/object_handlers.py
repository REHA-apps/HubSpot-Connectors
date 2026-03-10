from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, cast

from slack_sdk.web.async_client import AsyncWebClient

from app.connectors.hubspot_slack.ui.modal_builder import ModalBuilder
from app.core.logging import get_logger
from app.db.records import IntegrationRecord
from app.domains.messaging.slack.service import SlackMessagingService
from app.utils.constants import CREATE_RECORD_CALLBACK_ID

from .base import (
    InteractionContext,
    InteractionHandler,
    interaction_handler,
    with_slack_error_handling,
)

logger = get_logger("object_handlers")


class ObjectViewHandler(InteractionHandler):
    @interaction_handler("view_object")
    @with_slack_error_handling("view object")
    async def _handle_view_object(
        self,
        *,
        payload: Mapping[str, Any],
        integration: IntegrationRecord,
        messaging_service: SlackMessagingService,
        context: InteractionContext,
        **kwargs: Any,
    ) -> None:
        value = context.value or ""
        channel_id = context.channel_id
        parts = value.split(":")
        if len(parts) < 3:
            logger.warning("Malformed interaction value=%s", value)
            return
        obj_type = parts[1]
        obj_id = parts[2]
        obj = await self.hubspot.get_object(
            workspace_id=integration.workspace_id,
            object_type=obj_type,
            object_id=obj_id,
        )
        if not obj:
            logger.warning(
                "Could not find HubSpot object type=%s id=%s", obj_type, obj_id
            )
            return
        is_pro = await self.integration_service.is_pro_workspace(
            integration.workspace_id
        )
        analysis = await self.ai.analyze_polymorphic(obj, obj_type)
        await messaging_service.send_card(
            workspace_id=integration.workspace_id,
            obj=obj,
            analysis=analysis,
            channel=channel_id,
            is_pro=is_pro,
            response_url=context.response_url,
        )

    @interaction_handler("select_object")
    @with_slack_error_handling("update creation modal")
    async def _handle_select_object_type(
        self,
        *,
        payload: Mapping[str, Any],
        integration: IntegrationRecord,
        messaging_service: SlackMessagingService,
        context: InteractionContext,
        **kwargs: Any,
    ) -> None:
        """Handle selection of object type in creation modal."""
        actions = payload.get("actions", [])
        if not actions:
            return
        selected_option = actions[0].get("selected_option")
        if not selected_option:
            return
        object_type = selected_option.get("value")
        view_id = payload.get("view", {}).get("id")
        private_metadata = payload.get("view", {}).get("private_metadata", "{}")
        hubspot_client = await self.hubspot.get_client(integration.workspace_id)
        pipelines = None
        owners = None
        if object_type == "deal":
            pipelines = await hubspot_client.get_pipelines("deals")
            owners = await hubspot_client.get_owners()
        elif object_type == "ticket":
            pipelines = await hubspot_client.get_pipelines("tickets")
            owners = await hubspot_client.get_owners()
        elif object_type in ("task", "contact", "company"):
            owners = await hubspot_client.get_owners()
        modals = ModalBuilder()
        modal = modals.build_creation_modal(
            object_type=object_type,
            callback_id=CREATE_RECORD_CALLBACK_ID,
            pipelines=pipelines,
            owners=owners,
        )
        if private_metadata:
            if isinstance(private_metadata, dict):
                modal["private_metadata"] = json.dumps(private_metadata)
            else:
                modal["private_metadata"] = str(private_metadata)
        client = AsyncWebClient(token=integration.credentials.get("slack_bot_token"))
        await client.views_update(view_id=view_id, view=modal)

    @interaction_handler("view_contact_company")
    @with_slack_error_handling("fetch contact's company")
    async def _handle_view_contact_company(
        self,
        *,
        payload: Mapping[str, Any],
        integration: IntegrationRecord,
        messaging_service: SlackMessagingService,
        context: InteractionContext,
        **kwargs: Any,
    ) -> None:
        value = context.value or ""
        channel_id = context.channel_id
        parts = value.split(":")
        if len(parts) < 2:
            logger.warning("Malformed view_contact_company value=%s", value)
            return

        contact_id = parts[1]
        trigger_id = context.trigger_id
        view_id = None
        if trigger_id:
            view_id = await self._show_loading(
                trigger_id, "Associated Companies", integration
            )
        companies = await self.hubspot.get_associated_objects(
            workspace_id=integration.workspace_id,
            from_object_type="contact",
            object_id=contact_id,
            to_object_type="company",
        )
        cards = messaging_service.cards
        if not companies:
            card = cards.build_empty("No companies found for this contact.")
            success = False
            if view_id:
                success = await self._update_modal(
                    view_id, card, "Associated Companies", integration
                )
            if not success:
                response_url = cast(str, context.response_url)
                await messaging_service.send_via_response_url(
                    response_url=response_url,
                    text="Contact's Company",
                    blocks=messaging_service.slack_renderer.render(card)["blocks"],
                )
            return
        if len(companies) == 1:
            company = companies[0]
            analysis = await self.ai.analyze_polymorphic(company, "company")
            from app.domains.ai.service import AICompanyAnalysis

            card = messaging_service.cards.build_company(
                company, cast(AICompanyAnalysis, analysis), include_actions=False
            )
            success = False
            if view_id:
                success = await self._update_modal(
                    view_id, card, "Associated Company", integration
                )
            if not success:
                await messaging_service.send_card(
                    workspace_id=integration.workspace_id,
                    obj=company,
                    analysis=analysis,
                    channel=channel_id,
                    response_url=context.response_url,
                )
            return
        else:
            card = cards.build_search_results(companies)
        success = False
        if view_id:
            success = await self._update_modal(
                view_id, card, "Associated Companies", integration
            )
        if not success:
            rendered = messaging_service.slack_renderer.render(card)
            response_url = cast(str, context.response_url)
            if response_url:
                await messaging_service.send_via_response_url(
                    response_url=response_url,
                    text="Contact's Company",
                    blocks=rendered["blocks"],
                )
            else:
                await messaging_service.send_message(
                    workspace_id=integration.workspace_id,
                    text="Contact's Company",
                    blocks=rendered["blocks"],
                    channel=channel_id,
                )

    @interaction_handler("view_contact_deals")
    @with_slack_error_handling("fetch contact's deals")
    async def _handle_view_contact_deals(
        self,
        *,
        payload: Mapping[str, Any],
        integration: IntegrationRecord,
        messaging_service: SlackMessagingService,
        context: InteractionContext,
        **kwargs: Any,
    ) -> None:
        value = context.value or ""
        parts = value.split(":")
        if len(parts) < 2:
            logger.warning("Malformed view_contact_deals value=%s", value)
            return
        contact_id = parts[1]
        trigger_id = context.trigger_id
        view_id = None
        if trigger_id:
            view_id = await self._show_loading(
                trigger_id, "Associated Deals", integration
            )
        deals = await self.hubspot.get_associated_objects(
            workspace_id=integration.workspace_id,
            from_object_type="contact",
            object_id=contact_id,
            to_object_type="deal",
        )
        cards = messaging_service.cards
        if not deals:
            card = cards.build_empty("No deals found for this contact.")
        else:
            card = cards.build_deals_list(deals)
        success = False
        if view_id:
            success = await self._update_modal(
                view_id, card, "Associated Deals", integration
            )
        if not success:
            rendered = messaging_service.slack_renderer.render(card)
            response_url = cast(str, context.response_url)
            if response_url:
                await messaging_service.send_via_response_url(
                    response_url=response_url,
                    text="Contact's Deals",
                    blocks=rendered["blocks"],
                )

    @interaction_handler("view_company_deals")
    @with_slack_error_handling("fetch associated deals")
    async def _handle_view_company_deals(
        self,
        *,
        payload: Mapping[str, Any],
        integration: IntegrationRecord,
        messaging_service: SlackMessagingService,
        context: InteractionContext,
        **kwargs: Any,
    ) -> None:
        value = context.value or ""
        parts = value.split(":")
        if len(parts) < 2:
            logger.warning("Malformed view_company_deals value=%s", value)
            return
        company_id = parts[1]
        trigger_id = context.trigger_id
        view_id = None
        if trigger_id:
            view_id = await self._show_loading(
                trigger_id, "Associated Deals", integration
            )
        deals = await self.hubspot.get_associated_objects(
            workspace_id=integration.workspace_id,
            from_object_type="company",
            object_id=company_id,
            to_object_type="deal",
        )
        cards = messaging_service.cards
        if not deals:
            card = cards.build_empty("No deals found for this company.")
        else:
            card = cards.build_deals_list(deals)
        success = False
        if view_id:
            success = await self._update_modal(
                view_id, card, "Associated Deals", integration
            )
        if not success:
            rendered = messaging_service.slack_renderer.render(card)
            response_url = cast(str, context.response_url)
            if response_url:
                await messaging_service.send_via_response_url(
                    response_url=response_url,
                    text="Associated Deals",
                    blocks=rendered["blocks"],
                )

    @interaction_handler("view_deals")
    @with_slack_error_handling("fetch associated deals")
    async def _handle_view_deals(
        self,
        *,
        payload: Mapping[str, Any],
        integration: IntegrationRecord,
        messaging_service: SlackMessagingService,
        context: InteractionContext,
        **kwargs: Any,
    ) -> None:
        value = context.value or ""
        parts = value.split(":")
        if len(parts) < 2:
            logger.warning("Malformed view_deals value=%s", value)
            return
        contact_id = parts[1]
        trigger_id = context.trigger_id
        view_id = None
        if trigger_id:
            view_id = await self._show_loading(
                trigger_id, "Associated Deals", integration
            )
        deals = await self.hubspot.get_associated_objects(
            workspace_id=integration.workspace_id,
            from_object_type="contact",
            object_id=contact_id,
            to_object_type="deal",
        )
        cards = messaging_service.cards
        if not deals:
            card = cards.build_empty("No deals found for this contact.")
        else:
            card = cards.build_deals_list(deals)
        success = False
        if view_id:
            success = await self._update_modal(
                view_id, card, "Associated Deals", integration
            )
        if not success:
            rendered = messaging_service.slack_renderer.render(card)
            response_url = cast(str, context.response_url)
            if response_url:
                await messaging_service.send_via_response_url(
                    response_url=response_url,
                    text="Associated Deals",
                    blocks=rendered["blocks"],
                )

    @interaction_handler("view_contacts")
    @with_slack_error_handling("fetch associated contacts")
    async def _handle_view_contacts(
        self,
        *,
        payload: Mapping[str, Any],
        integration: IntegrationRecord,
        messaging_service: SlackMessagingService,
        context: InteractionContext,
        **kwargs: Any,
    ) -> None:
        value = context.value or ""
        parts = value.split(":")
        if len(parts) < 2:
            logger.warning("Malformed view_contacts value=%s", value)
            return
        company_id = parts[1]
        trigger_id = context.trigger_id
        view_id = None
        if trigger_id:
            view_id = await self._show_loading(
                trigger_id, "Associated Contacts", integration
            )
        contacts = await self.hubspot.get_associated_objects(
            workspace_id=integration.workspace_id,
            from_object_type="company",
            object_id=company_id,
            to_object_type="contact",
        )
        cards = messaging_service.cards
        if not contacts:
            card = cards.build_empty("No contacts found for this company.")
        else:
            card = cards.build_contacts_list(contacts)
        success = False
        if view_id:
            success = await self._update_modal(
                view_id, card, "Associated Contacts", integration
            )
        if not success:
            rendered = messaging_service.slack_renderer.render(card)
            response_url = cast(str, context.response_url)
            if response_url:
                await messaging_service.send_via_response_url(
                    response_url=response_url,
                    text="Associated Contacts",
                    blocks=rendered["blocks"],
                )

    @interaction_handler("view_contact_meetings")
    async def _handle_view_contact_meetings(
        self,
        *,
        payload: Mapping[str, Any],
        integration: IntegrationRecord,
        messaging_service: SlackMessagingService,
        context: InteractionContext,
        **kwargs: Any,
    ) -> None:
        value = context.value or ""
        channel_id = context.channel_id
        """Fetch and display meetings associated with a contact."""
        parts = value.split(":")
        if len(parts) < 2:
            logger.warning("Malformed view_contact_meetings value=%s", value)
            return
        try:
            contact_id = parts[1]
            trigger_id = context.trigger_id
            view_id = None
            if trigger_id:
                view_id = await self._show_loading(
                    trigger_id, "Associated Meetings", integration
                )
            meetings = await self.hubspot.get_contact_meetings(
                workspace_id=integration.workspace_id, contact_id=contact_id
            )
            cards = messaging_service.cards
            if not meetings:
                card = cards.build_empty("No meetings found for this contact.")
            else:
                from app.utils.transformers import to_datetime

                meetings.sort(
                    key=lambda x: to_datetime(
                        x.get("properties", {}).get("hs_meeting_start_time")
                    ),
                    reverse=True,
                )
                card = cards.build_meetings_list(meetings)
            if view_id:
                await self._update_modal(
                    view_id, card, "Associated Meetings", integration
                )
            elif trigger_id:
                await self._open_modal(
                    trigger_id=trigger_id,
                    view_or_card=card,
                    title="Associated Meetings",
                    integration=integration,
                )
            else:
                rendered = messaging_service.slack_renderer.render(card)
                response_url = cast(str, context.response_url)
                await messaging_service.send_via_response_url(
                    response_url=response_url,
                    text="Contact's Meetings",
                    blocks=rendered["blocks"],
                )
        except Exception as exc:
            logger.exception("Failed to view contact meetings: %s")
            response_url = context.response_url
            if response_url:
                await messaging_service.send_via_response_url(
                    response_url=response_url,
                    text=f"❌ Failed to fetch contact's meetings: {str(exc)}",
                )
            else:
                user_id = str(kwargs.get("payload", {}).get("user", {}).get("id", ""))
                if user_id:
                    client = AsyncWebClient(
                        token=integration.credentials.get("slack_bot_token")
                    )
                    if channel_id:
                        await client.chat_postEphemeral(
                            channel=channel_id,
                            user=user_id,
                            text=f"❌ Failed to fetch contact's meetings: {str(exc)}",
                        )
                    else:
                        try:
                            await client.chat_postMessage(
                                channel=user_id,
                                text=(
                                    f"❌ Failed to fetch contact's meetings: {str(exc)}"
                                ),
                            )
                        except Exception:
                            pass


class SuggestionHandler(InteractionHandler):
    @interaction_handler("association_search")
    async def _handle_association_search(
        self,
        *,
        payload: Mapping[str, Any],
        integration: IntegrationRecord,
        messaging_service: SlackMessagingService,
        context: InteractionContext,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Handles real-time search suggestions for the Association dropdown."""
        action_id = payload.get("action_id")
        value = payload.get("value", "")
        if action_id != "association_search":
            return {"options": []}
        logger.info("Performing association search for query: %s", value)
        try:
            hubspot_client = await self.hubspot.get_client(integration.workspace_id)
            import asyncio

            search_tasks = [
                hubspot_client.search_objects(
                    "contacts",
                    filters=[
                        {
                            "propertyName": "firstname",
                            "operator": "CONTAINS_TOKEN",
                            "value": value,
                        }
                    ],
                    limit=5,
                ),
                hubspot_client.search_objects(
                    "deals",
                    filters=[
                        {
                            "propertyName": "dealname",
                            "operator": "CONTAINS_TOKEN",
                            "value": value,
                        }
                    ],
                    limit=5,
                ),
                hubspot_client.search_objects(
                    "companies",
                    filters=[
                        {
                            "propertyName": "name",
                            "operator": "CONTAINS_TOKEN",
                            "value": value,
                        }
                    ],
                    limit=5,
                ),
            ]
            search_results = await asyncio.gather(*search_tasks)
            contacts_results, deals_results, companies_results = search_results
            options = []
            for obj in contacts_results:
                props = obj["properties"]
                name = (
                    f"{props.get('firstname', '')} {props.get('lastname', '')}".strip()
                    or props.get("email", "Unknown")
                )
                options.append(
                    {
                        "text": {"type": "plain_text", "text": f"👤 Contact: {name}"},
                        "value": f"contact:{obj['id']}",
                    }
                )
            for obj in deals_results:
                name = obj["properties"].get("dealname", "Unnamed Deal")
                options.append(
                    {
                        "text": {"type": "plain_text", "text": f"💰 Deal: {name}"},
                        "value": f"deal:{obj['id']}",
                    }
                )
            for obj in companies_results:
                name = obj["properties"].get("name", "Unnamed Company")
                options.append(
                    {
                        "text": {"type": "plain_text", "text": f"🏢 Company: {name}"},
                        "value": f"company:{obj['id']}",
                    }
                )
            return {"options": options[:25]}
        except Exception:
            logger.exception("Failed to fetch search suggestions: %s")
            return {"options": []}
