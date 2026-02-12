from fastapi import FastAPI, Depends
from fastapi.routing import APIRoute

from app.core.config import settings
from app.api.router import api_router
from app.api.deps import get_hubspot_connector, get_slack_connector

# ---------------------------
# FastAPI app
# ---------------------------
app = FastAPI(title=settings.APP_NAME)

# Include your API routers
app.include_router(api_router)


# ---------------------------
# Root endpoint
# ---------------------------
@app.get("/")
async def root():
    return {"message": f"{settings.APP_NAME} is running"}


# ---------------------------
# Startup event
# ---------------------------
@app.on_event("startup")
async def startup_event():
    """Print all registered routes on startup."""
    for route in api_router.routes:
        if isinstance(route, APIRoute):
            print(f"Path: {route.path} | Name: {route.name}")


# ---------------------------
# Dependency injection example
# ---------------------------
# Any router can now do:
# from fastapi import Depends
# hubspot: HubSpotConnector = Depends(get_hubspot_connector)
# slack: SlackConnector = Depends(get_slack_connector)
