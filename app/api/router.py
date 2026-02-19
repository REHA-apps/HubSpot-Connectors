# app/api/router.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.public.privacy_router import router as privacy_router
from app.api.public.terms_router import router as terms_router
from app.connectors.hubspot.routers.actions_router import (
    router as hubspot_actions_router,
)
from app.connectors.hubspot.routers.ai_cards_router import router as hubspot_ai_router
from app.connectors.hubspot.routers.install_router import (
    router as hubspot_install_router,
)
from app.connectors.hubspot.routers.oauth_router import router as hubspot_oauth
from app.connectors.hubspot.routers.webhook_router import (
    router as hubspot_webhook_router,
)
from app.connectors.slack.routers.events_router import router as slack_events_router
from app.connectors.slack.routers.install_router import router as install_router
from app.connectors.slack.routers.interactions_router import (
    router as slack_interactions_router,
)
from app.connectors.slack.routers.oauth_router import router as slack_oauth
from app.connectors.slack.routers.webhook_router import router as slack_webhook_router

api_router = APIRouter()


@api_router.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


# Slack install page
api_router.include_router(install_router)

# HubSpot install page
api_router.include_router(hubspot_install_router)

# Slack webhooks
api_router.include_router(slack_webhook_router)
api_router.include_router(slack_oauth)
api_router.include_router(slack_events_router)
api_router.include_router(slack_interactions_router)

# Public pages
api_router.include_router(privacy_router)
api_router.include_router(terms_router)

# HubSpot
api_router.include_router(hubspot_oauth)
api_router.include_router(hubspot_ai_router)
api_router.include_router(hubspot_actions_router)
api_router.include_router(hubspot_webhook_router)
