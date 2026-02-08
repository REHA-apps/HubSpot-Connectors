from fastapi import FastAPI
from app.api.hubspot import router as hubspot_router
from app.api.slack import router as slack_router
import app.core.config

app = FastAPI(title="HubSpot Connector Platform")

app.include_router(hubspot_router, prefix="/api/hubspot", tags=["HubSpot"])
app.include_router(slack_router, prefix="/api/slack", tags=["Slack"])

from fastapi.routing import APIRoute

for route in app.routes:
    if isinstance(route, APIRoute):
        print(f"Path: {route.path} | Name: {route.name}")
@app.get("/")
async def root():
    return {"message": "HubSpot Connector Platform is running"}
