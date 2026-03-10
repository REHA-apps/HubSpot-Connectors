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
    is_gated: bool = False


class UnifiedCard(BaseModel):
    """Description:
    Platform-agnostic intermediate representation of a CRM card or AI insight.
    """

    model_config = ConfigDict(frozen=True)

    title: str
    subtitle: str | None = None
    emoji: str | None = None
    badge: str | None = None  # e.g., "Free Version"

    # Key metrics (e.g., Score, Amount, Status)
    metrics: list[tuple[str, str]] = []

    # Primary textual content (Insights, Summaries)
    content: str | None = None

    # Secondary textual content (Next Actions, reasoning)
    secondary_content: list[tuple[str, str]] = []  # List of (Label, Text)

    actions: list[CardAction] = []
    footer: str | None = "Powered by REHA"


class ModalMetadata(BaseModel):
    """Description:
    Typed metadata for Slack modals to ensure robust parsing.
    """

    object_type: str | None = None
    object_id: str | None = None
    deal_id: str | None = None
    contact_id: str | None = None
    object_group: str | None = None
    stage_id: str | None = None
    channel_id: str | None = None
    response_url: str | None = None
    metadata_type: str | None = None  # e.g., "post_mortem", "next_step"
