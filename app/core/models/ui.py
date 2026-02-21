from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CardAction(BaseModel):
    model_config = ConfigDict(frozen=True)

    label: str
    action_type: str  # "url", "callback", "modal", "select"
    value: str
    url: str | None = None
    options: list[tuple[str, str]] | None = None  # [(label, value), ...]
    selected_option: str | None = None  # value of the currently selected option


class UnifiedCard(BaseModel):
    """Description:
    Platform-agnostic intermediate representation of a CRM card or AI insight.
    """

    model_config = ConfigDict(frozen=True)

    title: str
    subtitle: str | None = None
    emoji: str | None = None

    # Key metrics (e.g., Score, Amount, Status)
    metrics: list[tuple[str, str]] = []

    # Primary textual content (Insights, Summaries)
    content: str | None = None

    # Secondary textual content (Next Actions, reasoning)
    secondary_content: list[tuple[str, str]] = []  # List of (Label, Text)

    actions: list[CardAction] = []
    footer: str | None = "Powered by REHA"
