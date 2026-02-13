# app/services/task_service.py
from typing import Any

from app.clients.hubspot_client import HubSpotClient


async def create_hubspot_task(
    client: HubSpotClient, task_properties: dict[str, Any]
) -> dict[str, Any]:
    """Create a HubSpot task using the client."""
    return await client.create_task(task_properties)
