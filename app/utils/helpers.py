import httpx
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Callable, Optional
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from app.core.config import settings

class HTTPClient:
    """A singleton-like wrapper for httpx.AsyncClient to reuse connections."""
    _client: httpx.AsyncClient | None = None

    @classmethod
    def get_client(cls) -> httpx.AsyncClient:
        """Returns the global async client instance."""
        if cls._client is None or cls._client.is_closed:
            cls._client = httpx.AsyncClient(timeout=30.0)
        return cls._client

    @classmethod
    async def close(cls):
        """Closes the global async client instance."""
        if cls._client and not cls._client.is_closed:
            await cls._client.aclose()
            cls._client = None

async def send_slack_response(response_url: str, content: Dict[str, Any]):
    """Sends a response back to Slack using a response_url.
    
    Args:
        response_url: The URL provided by Slack to send the response to.
        content: The JSON payload to send.
    """
    client = HTTPClient.get_client()
    try:
        response = await client.post(response_url, json=content)
        response.raise_for_status()
    except Exception as e:
        # Log error or handle appropriately
        print(f"Failed to send Slack response: {e}")

async def send_slack_error(response_url: str, message: str):
    """Sends an error message to Slack.
    
    Args:
        response_url: The URL provided by Slack.
        message: The error message to display to the user.
    """
    await send_slack_response(response_url, {"text": f"❌ {message}"})

# --- Retry Decorator ---

def hubspot_retry():
    """Returns a tenacity retry decorator configured for HubSpot API calls."""
    return retry(
        wait=wait_exponential(multiplier=1, min=4, max=10),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type(httpx.HTTPStatusError),
        # You could also add dynamic checking for 429 specifically if needed
        reraise=True
    )

# --- Logging ---

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/api.log")
    ]
)
logger = logging.getLogger("crm-connectors")

def log_webhook_payload(payload: Dict[str, Any], trace_id: str):
    """Logs a webhook payload with a trace ID for debugging."""
    logger.info(f"TraceID: {trace_id} | Webhook Payload: {payload}")

