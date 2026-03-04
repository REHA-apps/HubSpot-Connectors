from __future__ import annotations

from app.core.models.ui import CardAction, UnifiedCard
from app.utils.transformers import to_datetime

from .components import ComponentsMixin

MAX_LIST_DISPLAY = 25
MAX_OWNERS_DISPLAY = 100


class ListCardsMixin(ComponentsMixin):
    def build_deals_list(self, deals: list[dict]) -> UnifiedCard:
        """Build a card showing a list of associated deals."""
        content_parts = []
        display_deals = deals[:25]
        for deal in display_deals:
            props = deal.get("properties", {})
            name = props.get("dealname") or "Unnamed Deal"
            amount = props.get("amount") or "N/A"
            stage = props.get("dealstage") or "unknown"
            content_parts.append(f"*{name}*\nAmount: `{amount}` • Stage: `{stage}`")

        if len(deals) > MAX_LIST_DISPLAY:
            content_parts.append(f"\n_...and {len(deals) - 25} more deals._")

        return UnifiedCard(
            title="Associated Deals",
            emoji="💰",
            content="\n\n".join(content_parts) if content_parts else "No deals found.",
        )

    def build_contacts_list(self, contacts: list[dict]) -> UnifiedCard:
        """Build a card showing a list of associated contacts."""
        content_parts = []
        display_contacts = contacts[:25]
        for contact in display_contacts:
            props = contact.get("properties", {})
            name = f"{props.get('firstname', '')} {props.get('lastname', '')}".strip()
            email = props.get("email") or "N/A"
            lifecycle = props.get("lifecyclestage") or "—"
            content_parts.append(
                f"*{name or email}*\nEmail: `{email}` • Stage: `{lifecycle}`"
            )

        if len(contacts) > MAX_LIST_DISPLAY:
            content_parts.append(f"\n_...and {len(contacts) - 25} more contacts._")

        return UnifiedCard(
            title="Associated Contacts",
            emoji="👥",
            content="\n\n".join(content_parts)
            if content_parts
            else "No contacts found.",
        )

    def build_meetings_list(self, meetings: list[dict]) -> UnifiedCard:
        """Build a card showing a list of associated meetings."""
        content_parts = []
        display_meetings = meetings[:25]
        for meeting in display_meetings:
            props = meeting.get("properties", {})
            title = props.get("hs_meeting_title") or "Untitled Meeting"

            # Start time
            start_ts = props.get("hs_meeting_start_time")
            start_str = "No time set"
            if start_ts:
                dt = to_datetime(start_ts)
                start_str = dt.strftime("%Y-%m-%d %H:%M")

            outcome = props.get("hs_meeting_outcome", "No outcome")
            content_parts.append(
                f"📅 *{title}*\nTime: `{start_str}` • Outcome: `{outcome}`"
            )

        if len(meetings) > MAX_LIST_DISPLAY:
            content_parts.append(f"\n_...and {len(meetings) - 25} more meetings._")

        return UnifiedCard(
            title="Associated Meetings",
            emoji="📅",
            content="\n\n".join(content_parts)
            if content_parts
            else "No meetings found.",
        )

    def build_search_results(self, results: list[dict]) -> UnifiedCard:
        if not results:
            return self.build_empty("No results found")

        count = len(results)
        actions = []
        for r in results:
            props = r.get("properties", {})

            # CRM objects use 'properties', CMS objects (like KB) use root attributes
            name = (
                props.get("name")
                or props.get("dealname")
                or props.get("subject")
                or props.get("hs_task_subject")
                or r.get("title")  # For Knowledge Articles
                or "Unknown"
            )

            # Add distinguishing detail so users can tell similar names apart
            detail = (
                props.get("domain")
                or props.get("email")
                or props.get("dealstage")
                or props.get("hs_pipeline_stage")
                or r.get("description")  # For Knowledge Articles
                or ""
            )
            label = f"{name} ({detail})" if detail else name

            # Truncate to 75 chars for Slack button text limit
            if len(label) > 75:  # noqa: PLR2004
                label = label[:72] + "..."

            actions.append(
                CardAction(
                    label=label,
                    action_type="callback",
                    value=f"view:{r.get('type')}:{r['id']}",
                )
            )

        return UnifiedCard(
            title="Search Results",
            subtitle=f"Found {count} matching records",
            emoji="🔍",
            content="Multiple results matched your query. Select one to view details:",
            actions=actions,
        )
