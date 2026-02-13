# app/api/router.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.hubspot import oauth_router as hubspot_oauth
from app.api.hubspot import webhook_router as hubspot_webhook
from app.api.slack import interactions_router as slack_interactions
from app.api.slack import oauth_router as slack_oauth
from app.api.slack import webhook_router as slack_webhook

api_router = APIRouter()

# HubSpot
api_router.include_router(hubspot_webhook.router)
api_router.include_router(hubspot_oauth.router)

# Slack
api_router.include_router(slack_webhook.router)
api_router.include_router(slack_oauth.router)
api_router.include_router(slack_interactions.router)
