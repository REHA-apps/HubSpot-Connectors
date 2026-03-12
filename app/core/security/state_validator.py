import base64
import hashlib
import hmac
import time

from app.core.config import settings


def sign_state(state: str) -> str:
    """Signs a state parameter with a timestamp and HMAC."""
    timestamp = str(int(time.time()))
    message = f"{state}:{timestamp}".encode()
    signature = hmac.new(
        settings.SLACK_SIGNING_SECRET.get_secret_value().encode(),
        message,
        hashlib.sha256,
    ).digest()

    encoded_sig = base64.urlsafe_b64encode(signature).decode().strip("=")
    return f"{state}.{timestamp}.{encoded_sig}"


def verify_state(signed_state: str, max_age: int = 600) -> str | None:
    """Verifies a signed state parameter and returns the original state if valid.

    Default max_age is 10 minutes (600 seconds).
    """
    try:
        parts = signed_state.split(".")
        if len(parts) != 3:  # noqa: PLR2004
            return None

        state, timestamp, signature = parts

        # Check expiration
        if int(time.time()) - int(timestamp) > max_age:
            return None

        # Verify signature
        message = f"{state}:{timestamp}".encode()
        expected_signature = hmac.new(
            settings.SLACK_SIGNING_SECRET.get_secret_value().encode(),
            message,
            hashlib.sha256,
        ).digest()

        encoded_expected = (
            base64.urlsafe_b64encode(expected_signature).decode().strip("=")
        )

        if hmac.compare_digest(encoded_expected, signature):
            return state

        return None
    except Exception:
        return None
