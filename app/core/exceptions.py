from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base category for all application-specific errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class IntegrationError(AppError):
    """Base for errors related to workspace/provider integrations."""

    pass


class IntegrationNotFoundError(IntegrationError):
    """Raised when an integration record is expected but not found."""

    pass


class HubSpotAPIError(AppError):
    """Raised when an external HubSpot API call fails."""

    pass


class SlackAPIError(AppError):
    """Raised when an external Slack API call fails."""

    pass


class AIServiceError(AppError):
    """Raised when AI analysis or heuristics fail."""

    pass
