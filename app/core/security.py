import hmac
import hashlib
import base64
import os
import time

_client_secret = os.getenv("HUBSPOT_CLIENT_SECRET")
if _client_secret is None:
    raise ValueError("HUBSPOT_CLIENT_SECRET environment variable is not set")
CLIENT_SECRET: str = _client_secret

_slack_signing_secret = os.getenv("SLACK_SIGNING_SECRET")
if _slack_signing_secret is None:
    raise ValueError("SLACK_SIGNING_SECRET environment variable is not set")
SLACK_SIGNING_SECRET: str = _slack_signing_secret

def verify_hubspot_signature(
    signature: str,
    request_body: bytes,
    url: str
) -> bool:
    digest = hmac.new(
        CLIENT_SECRET.encode(),
        msg=(url + request_body.decode()).encode(),
        digestmod=hashlib.sha256
    ).digest()

    computed = base64.b64encode(digest).decode()
    return hmac.compare_digest(computed, signature)


def verify_slack_signature(headers, body: bytes) -> bool:
    timestamp = headers.get("X-Slack-Request-Timestamp")
    signature = headers.get("X-Slack-Signature")

    if abs(time.time() - int(timestamp)) > 60 * 5:
        return False

    base = f"v0:{timestamp}:{body.decode()}"
    digest = hmac.new(
        SLACK_SIGNING_SECRET.encode(),
        base.encode(),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(f"v0={digest}", signature)
