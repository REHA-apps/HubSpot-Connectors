from __future__ import annotations

import re
from typing import Any

from app.core.models.ui import UnifiedCard


class HubSpotRenderer:
    """Converts a UnifiedCard IR into a modern React UI Extension JSON response.

    No legacy CRM card format (properties[], actions[], results[]) is emitted.
    All interactions are handled by React components in MirrorCard.tsx.
    """

    def render(
        self,
        object_id: str,
        card: UnifiedCard,
        object_type: str = "contact",
        engagements: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return {
            "objectId": object_id,
            "title": card.title or "CRM Insights",
            "subtitle": card.subtitle,
            "emoji": card.emoji,
            "badge": card.badge,
            "content": card.content,
            "metrics": card.metrics,
            "secondary_content": card.secondary_content,
            "engagements": _serialize_engagements(engagements or []),
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
            detail = props.get("hs_call_body") or ""
            date = props.get("hs_timestamp") or props.get("createdate") or ""
            icon = "📞"
        elif etype == "meetings":
            subject = props.get("hs_meeting_title") or "Meeting"
            detail = props.get("hs_meeting_body") or ""
            outcome = props.get("hs_meeting_outcome") or ""
            if outcome:
                detail = f"Outcome: {outcome}. {detail}".strip()
            date = props.get("hs_meeting_start_time") or props.get("createdate") or ""
            icon = "📅"
        elif etype == "tasks":
            subject = props.get("hs_task_subject") or "Task"
            detail = props.get("hs_task_body") or ""
            status = props.get("hs_task_status") or ""
            priority = props.get("hs_task_priority") or ""
            meta = " • ".join(filter(None, [status, priority]))
            if meta:
                detail = f"{meta}. {detail}".strip()
            date = props.get("hs_timestamp") or props.get("createdate") or ""
            icon = "✅"
        else:
            subject = "Activity"
            detail = ""
            date = props.get("createdate") or ""
            icon = "📌"

        # Trim detail to 200 chars
        if len(detail) > 200:  # noqa: PLR2004
            detail = detail[:197] + "..."

        out.append(
            {
                "type": etype,
                "icon": icon,
                "subject": subject,
                "detail": detail,
                "date": date[:10] if date else "",  # just YYYY-MM-DD
            }
        )

    # Sort newest first by date string (ISO format sorts lexicographically)
    out.sort(key=lambda x: x["date"], reverse=True)
    return out[:10]


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
