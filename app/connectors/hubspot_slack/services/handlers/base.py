from __future__ import annotations

import inspect
from abc import ABC
from collections.abc import Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import wraps
from typing import Any, TypeVar

from app.core.logging import get_logger
from app.core.models.ui import UnifiedCard
from app.db.records import IntegrationRecord
from app.domains.ai.service import AIService
from app.domains.crm.hubspot.service import HubSpotService
from app.domains.crm.integration_service import IntegrationService
from app.domains.crm.ui.card_builder import CardBuilder
from app.domains.messaging.slack.service import SlackMessagingService

logger = get_logger("base_handler")

T = TypeVar("T")


@dataclass
class InteractionContext:
    user_id: str
    team_id: str
    channel_id: str | None = None
    response_url: str | None = None
    trigger_id: str | None = None
    action_id: str | None = None
    value: str | None = None
    corr_id: str | None = None

    @classmethod
    def from_payload(
        cls, payload: Mapping[str, Any], **kwargs: Any
    ) -> InteractionContext:
        user_id = payload.get("user", {}).get("id", "")
        team_id = payload.get("team", {}).get("id", "")
        channel_id = payload.get("channel", {}).get("id") or kwargs.get("channel_id")
        response_url = payload.get("response_url") or kwargs.get("response_url")
        trigger_id = payload.get("trigger_id") or kwargs.get("trigger_id")
        action_id = kwargs.get("action_id")
        value = kwargs.get("value")
        corr_id = kwargs.get("corr_id")

        return cls(
            user_id=user_id,
            team_id=team_id,
            channel_id=channel_id,
            response_url=response_url,
            trigger_id=trigger_id,
            action_id=action_id,
            value=value,
            corr_id=corr_id,
        )


def interaction_handler(
    *actions: str,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register a method as a handler for specific actions or callback IDs."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        setattr(func, "__interaction_actions__", list(actions))
        return func

    return decorator


def with_slack_error_handling(
    action_name: str,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to catch exceptions, log with traceback, and notify user via Slack."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            try:
                return await func(self, *args, **kwargs)
            except Exception as exc:
                logger.exception("Failed to %s", action_name)

                # Try to extract context/kwargs for response_url
                payload = kwargs.get("payload") or (args[0] if args else {})
                messaging_service: SlackMessagingService | None = kwargs.get(
                    "messaging_service"
                )

                response_url = kwargs.get("response_url")
                if not response_url and isinstance(payload, dict):
                    response_url = payload.get("response_url")

                user_id = kwargs.get("user_id")
                if not user_id and isinstance(payload, dict):
                    user_id = payload.get("user", {}).get("id")

                if response_url and messaging_service:
                    try:
                        await messaging_service.send_via_response_url(
                            response_url=str(response_url),
                            text=f"❌ Failed to {action_name}: {str(exc)}",
                        )
                    except Exception as inner_exc:
                        logger.error(
                            "Failed to send error to response_url: %s", inner_exc
                        )
                elif user_id and messaging_service:
                    try:
                        slack_channel = await messaging_service.get_slack_channel()
                        client = slack_channel.get_slack_client()
                        await client.chat_postMessage(
                            channel=user_id,
                            text=f"❌ Failed to {action_name}: {str(exc)}",
                        )
                    except Exception as inner_exc:
                        logger.error(
                            "Failed to post error message to user: %s", inner_exc
                        )

        return wrapper

    return decorator


@asynccontextmanager
async def slack_error_handling(
    action_name: str,
    payload: Mapping[str, Any],
    messaging_service: SlackMessagingService | None = None,
    user_id: str | None = None,
    response_url: str | None = None,
):
    """Context manager to catch exceptions and notify user via Slack."""
    try:
        yield
    except Exception as exc:
        logger.exception("Failed to %s", action_name)
        if not response_url and isinstance(payload, dict):
            response_url = payload.get("response_url")
        if not user_id and isinstance(payload, dict):
            user_id = payload.get("user", {}).get("id")

        if response_url and messaging_service:
            try:
                await messaging_service.send_via_response_url(
                    response_url=str(response_url),
                    text=f"❌ Failed to {action_name}: {str(exc)}",
                )
            except Exception as inner_exc:
                logger.error("Failed to send error to response_url: %s", inner_exc)
        elif user_id and messaging_service:
            try:
                slack_channel = await messaging_service.get_slack_channel()
                client = slack_channel.get_slack_client()
                await client.chat_postMessage(
                    channel=str(user_id), text=f"❌ Failed to {action_name}: {str(exc)}"
                )
            except Exception as inner_exc:
                logger.error("Failed to post error message to user: %s", inner_exc)


class InteractionHandler(ABC):
    def __init__(
        self,
        corr_id: str,
        hubspot: HubSpotService,
        ai: AIService,
        integration_service: IntegrationService,
    ):
        self.corr_id = corr_id
        self.hubspot = hubspot
        self.ai = ai
        self.integration_service = integration_service

        # Automatically register methods decorated with @interaction_handler
        self._action_routes: dict[str, Callable[..., Any]] = {}
        for _, method in inspect.getmembers(self, inspect.ismethod):
            actions = getattr(method, "__interaction_actions__", [])
            for action in actions:
                self._action_routes[action] = method

    async def handle(
        self,
        payload: Mapping[str, Any],
        integration: IntegrationRecord,
        messaging_service: SlackMessagingService,
        **kwargs: Any,
    ) -> Any:
        # Determine the action identifier (action_id or callback_id)
        action_id = kwargs.get("action_id")
        if not action_id:
            action_id = payload.get("view", {}).get("callback_id")

        if not action_id:
            logger.warning("No action_id or callback_id found in payload")
            return None

        for registered_action, method in self._action_routes.items():
            if action_id == registered_action or action_id.startswith(
                f"{registered_action}:"
            ):
                # Call the dynamically resolved method
                # pass kwargs explicitly and payload for extraction.
                context = InteractionContext.from_payload(payload, **kwargs)
                return await method(
                    payload=payload,
                    integration=integration,
                    messaging_service=messaging_service,
                    context=context,
                    **kwargs,
                )

        logger.warning(
            "No dynamic route found for action_id=%s in %s",
            action_id,
            self.__class__.__name__,
        )
        return None

    async def _show_loading(
        self, trigger_id: str, title: str, integration: IntegrationRecord
    ) -> str | None:
        """Opens a loading modal immediately to secure the trigger_id window."""
        bot_token = integration.credentials.get("slack_bot_token")
        if not bot_token:
            return None
        try:
            from app.domains.crm.ui.card_builder import CardBuilder

            builder = CardBuilder()
            modal = builder.build_loading_modal(title=title)
            client = await self.integration_service.get_slack_client(integration)
            resp = await client.views_open(trigger_id=trigger_id, view=modal)
            if not resp or not resp.get("ok"):
                logger.error(
                    "Failed to show loading modal: %s",
                    resp.get("error") if resp else "No response",
                )
                return None
            view = resp.get("view")
            if not view or not isinstance(view, dict):
                return None
            return str(view.get("id"))
        except Exception:
            logger.exception("Failed to show loading modal: %s")
            return None

    async def _update_modal(
        self,
        view_id: str,
        view_or_card: dict[str, Any] | UnifiedCard,
        title: str,
        integration: IntegrationRecord,
    ) -> bool:
        """Updates an existing Slack modal with final content."""
        bot_token = integration.credentials.get("slack_bot_token")
        if not bot_token:
            return False
        try:
            from app.domains.crm.ui.card_builder import CardBuilder

            if isinstance(view_or_card, dict):
                modal = view_or_card
            else:
                builder = CardBuilder()
                modal = builder.build_card_modal(view_or_card, title=title)
            client = await self.integration_service.get_slack_client(integration)
            await client.views_update(view_id=view_id, view=modal)
            logger.info("Modal updated for view_id=%s", view_id[:8])
            return True
        except Exception as exc:
            logger.error("Failed to update modal '%s': %s", title, exc)
            return False

    async def _open_modal(
        self,
        trigger_id: str | None,
        view_or_card: dict[str, Any] | UnifiedCard,
        title: str,
        integration: IntegrationRecord,
    ) -> str | None:
        """Helper to render a UnifiedCard or use a raw View and open it as a
        Slack modal.

        # noqa: E501
        """
        if not trigger_id:
            logger.error("Missing trigger_id for opening modal: %s", title)
            return None
        bot_token = integration.credentials.get("slack_bot_token")
        if not bot_token:
            logger.error("Missing bot token for opening modal")
            return None
        try:
            from app.domains.crm.ui.card_builder import CardBuilder

            if isinstance(view_or_card, dict):
                modal = view_or_card
            else:
                builder = CardBuilder()
                modal = builder.build_card_modal(view_or_card, title=title)
            client = await self.integration_service.get_slack_client(integration)
            resp = await client.views_open(trigger_id=trigger_id, view=modal)
            if not resp or not resp.get("ok"):
                logger.error(
                    "Failed to open modal '%s': %s",
                    title,
                    resp.get("error") if resp else "No response",
                )
                return None
            view = resp.get("view")
            if not view or not isinstance(view, dict):
                return None
            logger.info("Modal '%s' opened for trigger_id=%s", title, trigger_id[:8])
            return str(view.get("id"))
        except Exception as exc:
            logger.error("Failed to open modal '%s': %s", title, exc, exc_info=True)
            return None

    async def _handle_gated_click(
        self,
        feature_id: str,
        trigger_id: str | None,
        integration: IntegrationRecord,
        messaging_service: SlackMessagingService,
    ) -> None:
        """Shows the upgrade nudge modal when a gated feature is clicked.

        Args:
            feature_id: The ID of the feature they tried to access.
            trigger_id: The trigger ID from Slack to open a modal.
            integration: The integration record.
            messaging_service: The messaging service for Slack API calls.

        """
        if not trigger_id:
            return
        builder = CardBuilder()
        modal = builder.build_upgrade_nudge_modal(feature_name=feature_id)
        client = await self.integration_service.get_slack_client(integration)
        await client.views_open(trigger_id=trigger_id, view=modal)
