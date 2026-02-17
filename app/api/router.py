# app/api/router.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.hubspot import oauth_router as hubspot_oauth
from app.api.slack import oauth_router as slack_oauth
from app.api.slack.events_router import router as slack_events_router
from app.api.slack.webhook_router import router as slack_webhook_router
from app.api.hubspot.ai_cards_router import router as hubspot_ai_router
from app.api.hubspot.actions_router import router as hubspot_actions_router
from app.api.slack.install_router import router as install_router
from app.api.public.privacy_router import router as privacy_router
from app.api.public.terms_router import router as terms_router
from app.api.hubspot.install_router import router as hubspot_install_router

api_router = APIRouter()

@api_router.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}

@api_router.get("/")
async def root() -> dict[str, str]:
    return {"message": "CRM Connector API is running"}

# Slack install page
api_router.include_router(install_router)

# HubSpot install page
api_router.include_router(hubspot_install_router)

# Slack webhooks
api_router.include_router(slack_webhook_router)
api_router.include_router(slack_oauth.router)
api_router.include_router(slack_events_router)

# Public pages
api_router.include_router(privacy_router)
api_router.include_router(terms_router)

# HubSpot
api_router.include_router(hubspot_oauth.router)
api_router.include_router(hubspot_ai_router)
api_router.include_router(hubspot_actions_router)