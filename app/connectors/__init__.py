from __future__ import annotations


def setup_connectors():
    """Register all available connectors with deferred imports."""
    # HubSpot Routers
    from app.connectors.hubspot.routers.actions_router import (  # noqa: PLC0415
        router as hs_actions,
    )
    from app.connectors.hubspot.routers.ai_cards_router import (  # noqa: PLC0415
        router as hs_ai,
    )
    from app.connectors.hubspot.routers.extensions_router import (  # noqa: PLC0415
        router as hs_ext,
    )
    from app.connectors.hubspot.routers.install_router import (  # noqa: PLC0415
        router as hs_install,
    )
    from app.connectors.hubspot.routers.oauth_router import (  # noqa: PLC0415
        router as hs_oauth,
    )
    from app.connectors.hubspot.routers.ui_extension_router import (  # noqa: PLC0415
        router as hs_ui_ext,
    )
    from app.connectors.hubspot.routers.webhook_router import (  # noqa: PLC0415
        router as hs_webhook,
    )
    from app.connectors.hubspot.routers.workflow_actions_router import (  # noqa: PLC0415
        router as hs_workflow,
    )
    from app.connectors.registry import registry  # noqa: PLC0415

    # Slack Routers
    from app.connectors.slack.routers.events_router import (  # noqa: PLC0415
        router as slack_events,
    )
    from app.connectors.slack.routers.install_router import (  # noqa: PLC0415
        router as slack_install,
    )
    from app.connectors.slack.routers.interactions_router import (  # noqa: PLC0415
        router as slack_interactions,
    )
    from app.connectors.slack.routers.oauth_router import (  # noqa: PLC0415
        router as slack_oauth,
    )
    from app.connectors.slack.routers.webhook_router import (  # noqa: PLC0415
        router as slack_webhook,
    )

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
        ],
    )

    # Slack Registration
    from app.connectors.slack.renderer import SlackRenderer  # noqa: PLC0415
    from app.connectors.slack.services.channel_service import (  # noqa: PLC0415
        ChannelService,
    )
    from app.connectors.slack.services.service import (  # noqa: PLC0415
        InteractionService,
    )

    registry.register(
        name="slack",
        renderer=SlackRenderer,
        service=InteractionService,
        channel_service=ChannelService,
        routers=[
            slack_install,
            slack_webhook,
            slack_oauth,
            slack_events,
            slack_interactions,
        ],
    )
