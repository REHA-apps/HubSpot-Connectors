from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.core.models.ui import UnifiedCard


class HubSpotRenderer:
    """Converts a UnifiedCard IR into a modern React UI Extension JSON response.

    Emits only AI-unique data that complements (not duplicates) the native
    HubSpot sidebar.  Basic contact/company/deal properties are already
    visible in the record header and association cards.
    """

    # Metrics worth showing — everything else duplicates the native sidebar
    _AI_METRIC_KEYS = frozenset(
        {
            "Score",
            "Risk",
            "Health",
            "Urgency",
            "Status",
            "Priority",
            "Stage",
            "Assigned To",
            "Due",
        }
    )

    def render(
        self,
        object_id: str,
        card: UnifiedCard,
        object_type: str = "contact",
        engagements: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        # Only keep metrics that add AI value
        ai_metrics = [
            m
            for m in (card.metrics or [])
            if m[0] in self._AI_METRIC_KEYS or m[0] == "Lead Score"
        ]

        # Suppress engagements for deals as they duplicate native cards too much
        display_engagements = engagements or []
        if object_type.lower() in {"deal", "0-3"}:
            display_engagements = []

        return {
            "objectId": object_id,
            "title": card.title or "CRM Insights",
            "subtitle": card.subtitle,
            "emoji": card.emoji,
            "badge": card.badge,
            "content": card.content,
            "metrics": ai_metrics,
            "secondary_content": card.secondary_content,
            "engagements": _serialize_engagements(display_engagements),
        }


def _serialize_engagements(raw: list[dict]) -> list[dict]:
    """Normalize raw engagement dicts into a compact, frontend-friendly list."""
    out = []
    for e in raw:
        props = e.get("properties") or {}
        etype = e.get("_engagement_type", "engagement")

        # Extract type-specific fields
        if etype == "emails":
            subject = props.get("hs_email_subject") or "Email"
            detail = _extract_email_preview(props.get("hs_email_text") or "")
            date = props.get("hs_timestamp") or props.get("createdate") or ""
            icon = "✉️"
        elif etype == "calls":
            subject = props.get("hs_call_title") or "Call"
            detail = _strip_html(props.get("hs_call_body") or "")
            date = props.get("hs_timestamp") or props.get("createdate") or ""
            icon = "📞"
        elif etype == "meetings":
            subject = props.get("hs_meeting_title") or "Meeting"
            detail = _strip_html(props.get("hs_meeting_body") or "")
            outcome = props.get("hs_meeting_outcome") or ""
            if outcome:
                detail = f"Outcome: {outcome}. {detail}".strip()
            date = props.get("hs_meeting_start_time") or props.get("createdate") or ""
            icon = "📅"
        elif etype == "tasks":
            subject = props.get("hs_task_subject") or "Task"
            detail = _strip_html(props.get("hs_task_body") or "")
            status = props.get("hs_task_status") or ""
            priority = props.get("hs_task_priority") or ""
            meta = " • ".join(filter(None, [status, priority]))
            if meta:
                detail = f"{meta}. {detail}".strip()
            date = props.get("hs_timestamp") or props.get("createdate") or ""
            icon = "✅"
        elif etype == "notes":
            subject = "Note"
            detail = _strip_html(props.get("hs_note_body") or "")
            date = props.get("hs_timestamp") or props.get("createdate") or ""
            icon = "📝"
        else:
            subject = "Activity"
            detail = ""
            date = props.get("createdate") or ""
            icon = "📌"

        # Trim detail to 200 chars
        if len(detail) > 200:  # noqa: PLR2004
            detail = detail[:197] + "..."

        # Format date as English string to avoid auto-localization in HubSpot UI
        date_str = ""
        if date:
            try:
                # HubSpot dates are often ISO or YYYY-MM-DD
                dt = datetime.fromisoformat(date.replace("Z", "+00:00"))
                date_str = dt.strftime("%b %d, %Y")
            except Exception:
                date_str = date[:10]

        out.append(
            {
                "type": etype,
                "icon": icon,
                "subject": subject,
                "detail": detail,
                "date": date_str,
            }
        )

    # Sort newest first by date string (ISO format sorts lexicographically)
    out.sort(key=lambda x: x["date"], reverse=True)
    return out[:5]


def _extract_email_preview(raw: str) -> str:
    """Extract a clean, meaningful preview from a raw HubSpot email body.

    Strips HTML tags, removes quoted reply chains, collapses whitespace,
    and returns the first ~180 chars of original content only.
    This gives useful context without dumping the full email body.
    """
    text = raw

    # 1. Strip HTML tags
    text = re.sub(r"<[^>]+>", " ", text)

    # 2. Decode common HTML entities
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
    )

    # 3. Remove quoted reply block: "On <date> <name> wrote:" and everything after
    text = re.sub(
        r"(?s)(On\s.{1,100}wrote:|-----Original Message-----|From:\s+\S).+",
        "",
        text,
    )

    # 4. Remove lines that start with ">" (inline quoting)
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith(">")]
    text = " ".join(lines)

    # 5. Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()

    # 6. Return first 180 chars, ending at a sentence boundary if possible
    if len(text) <= 180:  # noqa: PLR2004
        return text

    trimmed = text[:180]
    # Try to end at last sentence boundary
    for sep in (".", "!", "?"):
        idx = trimmed.rfind(sep)
        if idx > 80:  # noqa: PLR2004
            return trimmed[: idx + 1]

    return trimmed.rsplit(" ", 1)[0] + "…"


def _strip_html(raw: str) -> str:
    """Remove HTML tags and decode basic entities from a string.

    Also collapses multiple spaces/newlines into single spaces.
    """
    if not raw:
        return ""
    text = str(raw)
    # Strip tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode some common entities
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
    )
    # Collapse whitespace
    return re.sub(r"\s+", " ", text).strip()
