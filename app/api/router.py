# app/api/router.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.hubspot import oauth_router as hubspot_oauth
from app.api.hubspot import webhook_router as hubspot_webhook
from app.api.slack import interactions_router as slack_interactions
from app.api.slack import oauth_router as slack_oauth
from app.api.slack.events_router import router as slack_events_router
from app.api.slack.webhook_router import router as slack_webhook_router

api_router = APIRouter()


# ---------------------------------------------------------
# Health / Root
# ---------------------------------------------------------
@api_router.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@api_router.get("/")
async def root() -> dict[str, str]:
    return {"message": "CRM Connector API is running"}


# ---------------------------------------------------------
# HubSpot Routes
# ---------------------------------------------------------
api_router.include_router(hubspot_webhook.router)
api_router.include_router(hubspot_oauth.router)


# ---------------------------------------------------------
# Slack Routes
# ---------------------------------------------------------
api_router.include_router(slack_webhook_router)
api_router.include_router(slack_oauth.router)
api_router.include_router(slack_interactions.router)
api_router.include_router(slack_events_router)
