from fastapi import APIRouter
from app.api.hubspot import webhook_router, oauth_router as hubspot_oauth
from app.api.slack import interactions_router, webhook_router as slack_webhook, oauth_router as slack_oauth

api_router = APIRouter()

# HubSpot
api_router.include_router(webhook_router.router)
api_router.include_router(hubspot_oauth.router)

# Slack
api_router.include_router(interactions_router.router)
api_router.include_router(slack_webhook.router)
api_router.include_router(slack_oauth.router)
