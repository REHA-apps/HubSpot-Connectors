from fastapi import FastAPI
from app.connectors.hubspot.oauth import router as hubspot_oauth
from app.connectors.hubspot.webhooks import router as hubspot_webhooks
import app.core.config
from app.connectors.slack.oauth import router as slack_oauth
from app.connectors.slack.commands import router as slack_commands
from app.connectors.slack.interactions import router as slack_interactions

app = FastAPI(title="CRM Connector Platform")

app.include_router(hubspot_oauth, prefix="/oauth/hubspot")
app.include_router(slack_oauth, prefix="/oauth/slack")
app.include_router(hubspot_webhooks, prefix="/webhooks/hubspot")
app.include_router(slack_commands, prefix="/slack")
app.include_router(slack_interactions, prefix="/slack")
