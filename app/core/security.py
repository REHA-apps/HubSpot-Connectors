import hmac
import hashlib
import base64
import time
from app.core.config import settings

def verify_hubspot_signature(
    signature: str,
    request_body: bytes,
    url: str
) -> bool:
    """Verifies the HubSpot signature for incoming webhooks.
    
    Args:
        signature: The X-HubSpot-Signature header value.
        request_body: The raw request body bytes.
        url: The full request URL.
        
    Returns:
        True if the signature is valid, False otherwise.
    """
    if not settings.HUBSPOT_CLIENT_SECRET:
        return False

    digest = hmac.new(
        settings.HUBSPOT_CLIENT_SECRET.encode(),
        msg=(url + request_body.decode()).encode(),
        digestmod=hashlib.sha256
    ).digest()

    computed = base64.b64encode(digest).decode()
    return hmac.compare_digest(computed, signature)


from typing import Mapping

def verify_slack_signature(headers: Mapping[str, str], body: bytes) -> bool:
    """Verifies the Slack signature for incoming commands/interactions.
    
    Args:
        headers: The request headers.
        body: The raw request body bytes.
        
    Returns:
        True if the signature is valid, False otherwise.
    """
    timestamp = headers.get("X-Slack-Request-Timestamp")
    signature = headers.get("X-Slack-Signature")

    if not timestamp or not signature or not settings.SLACK_SIGNING_SECRET:
        return False

    try:
        if abs(time.time() - int(timestamp)) > 60 * 5:
            return False
    except (ValueError, TypeError):
        return False

    base = f"v0:{timestamp}:{body.decode()}"
    digest = hmac.new(
        settings.SLACK_SIGNING_SECRET.encode(),
        base.encode(),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(f"v0={digest}", signature)
