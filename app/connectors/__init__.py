from __future__ import annotations


def setup_connectors():
    """Register all available connectors with deferred imports."""
    # HubSpot-Slack Unified Routers
    from app.connectors.hubspot_slack.routers.hubspot.actions_router import (
        router as hs_actions,
    )
    from app.connectors.hubspot_slack.routers.hubspot.ai_cards_router import (
        router as hs_ai,
    )
    from app.connectors.hubspot_slack.routers.hubspot.billing_router import (
        router as hs_billing,
    )
    from app.connectors.hubspot_slack.routers.hubspot.extensions_router import (
        router as hs_ext,
    )
    from app.connectors.hubspot_slack.routers.hubspot.install_router import (
        router as hs_install,
    )
    from app.connectors.hubspot_slack.routers.hubspot.oauth_router import (
        router as hs_oauth,
    )
    from app.connectors.hubspot_slack.routers.hubspot.settings_router import (
        router as hs_settings,
    )
    from app.connectors.hubspot_slack.routers.hubspot.ui_extension_router import (
        router as hs_ui_ext,
    )
    from app.connectors.hubspot_slack.routers.hubspot.webhook_router import (
        router as hs_webhook,
    )
    from app.connectors.hubspot_slack.routers.hubspot.workflow_actions_router import (
        router as hs_workflow,
    )

    # Slack Routers
    from app.connectors.hubspot_slack.routers.slack.events_router import (
        router as slack_events,
    )
    from app.connectors.hubspot_slack.routers.slack.install_router import (
        router as slack_install,
    )
    from app.connectors.hubspot_slack.routers.slack.interactions_router import (
        router as slack_interactions,
    )
    from app.connectors.hubspot_slack.routers.slack.oauth_router import (
        router as slack_oauth,
    )
    from app.connectors.hubspot_slack.routers.slack.webhook_router import (
        router as slack_webhook,
    )
    from app.connectors.registry import registry

    # HubSpot Registration
    registry.register(
        name="hubspot",
        routers=[
            hs_oauth,
            hs_ai,
            hs_actions,
            hs_ext,
            hs_webhook,
            hs_workflow,
            hs_install,
            hs_ui_ext,
            hs_settings,
            hs_billing,
        ],
    )

    # Slack Registration
    from app.connectors.hubspot_slack.services.service import (
        InteractionService,
    )
    from app.connectors.hubspot_slack.slack_renderer import SlackRenderer
    from app.domains.messaging.slack.service import SlackMessagingService

    registry.register(
        name="slack",
        renderer=SlackRenderer,
        service=InteractionService,
        channel_service=SlackMessagingService,
        routers=[
            slack_install,
            slack_webhook,
            slack_oauth,
            slack_events,
            slack_interactions,
        ],
    )
