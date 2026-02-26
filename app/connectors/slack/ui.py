from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any, cast

from app.core.models.ui import CardAction, UnifiedCard
from app.domains.ai.service import (
    AICompanyAnalysis,
    AIContactAnalysis,
    AIConversationAnalysis,
    AIDealAnalysis,
    AITaskAnalysis,
    AIThreadSummary,
    AITicketAnalysis,
)
from app.utils.transformers import to_datetime

MAX_LIST_DISPLAY = 25
MAX_OWNERS_DISPLAY = 100


class CardBuilder:
    """Description:
        Unified utility for building platform-agnostic CRM and AI insight cards.

    Rules Applied:
        - Returns UnifiedCard IR.
        - Centralizes rendering logic for Contacts, Deals, Companies, Tickets,
          and Tasks.
    """

    def build_card_modal(self, card: UnifiedCard, title: str = "Details") -> dict:
        """Wraps a UnifiedCard into a Slack Modal payload.

        Args:
            card (UnifiedCard): The unified card data structure to render.
            title (str, optional): The title of the modal. Defaults to "Details".

        Returns:
            dict: A Slack modal payload containing the rendered card blocks.

        """
        from app.connectors.slack.renderer import SlackRenderer

        renderer = SlackRenderer()
        payload = renderer.render(card)

        return {
            "type": "modal",
            "title": {"type": "plain_text", "text": title[:24]},
            "blocks": payload["blocks"],
            "close": {"type": "plain_text", "text": "Close"},
        }

    def build_app_home_view(self) -> dict[str, Any]:
        """Provides a static Home tab dashboard layout for the App Home view.

        Returns:
            dict[str, Any]: The Slack Home tab view payload.

        """
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🏠 Welcome to HubSpot CRM Connector",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "Search HubSpot contacts, companies, deals, tickets, and tasks "
                        "directly from Slack. Access CRM data seamlessly without "
                        "switching apps!"
                    ),
                },
            },
            {"type": "divider"},
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "⚡ Available Commands",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "- `/hs <query>` - Smart AI search across entire CRM\n"
                        "- `/hs` `/hs help` `/hs-help` - "
                        "Show help and available commands\n"
                        "- `/hs report` `/hs-reports` - View HubSpot dashboards\n"
                        "- `/hs-companies <domain or name>` - Search Companies\n"
                        "- `/hs-contacts <email or name>` - Search Contacts\n"
                        "- `/hs-deals <deal name>` - Search Deals\n"
                        "- `/hs-tickets <subject or ID>` - Search Tickets\n"
                        "- `/hs-tasks <task name>` - Search Tasks"
                    ),
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "💡 *Quick Tip*: You can quickly create new CRM records "
                        "directly in Slack using the `Create HubSpot Record` "
                        "shortcut from the global Shortcuts menu."
                    ),
                },
            },
        ]

        return {"type": "home", "blocks": blocks}

    def build_contact(
        self, obj: Mapping[str, Any], analysis: AIContactAnalysis, is_pro: bool = False
    ) -> UnifiedCard:
        """Builds a UnifiedCard representation for a HubSpot Contact.

        Args:
            obj (Mapping[str, Any]): Raw HubSpot contact object.
            analysis (AIContactAnalysis): Pre-calculated AI insights and scores.
            is_pro (bool, optional): Whether the workspace is in the PRO tier.
                Defaults to False.

        Returns:
            UnifiedCard: The rendered IR for Slack or other platforms.

        """
        props = obj["properties"]
        name = f"{props.get('firstname', '')} {props.get('lastname', '')}".strip()
        email = props.get("email", "unknown@example.com")

        job_title = props.get("jobtitle")
        subtitle = f"Contact | {job_title}" if job_title else "Contact"

        phone = str(props.get("phone") or "")
        mobile = str(props.get("mobilephone") or "")

        metrics = [
            ("Email", str(props.get("email") or "N/A")),
        ]
        if phone:
            metrics.append(("Phone", f"tel:{phone}"))
        else:
            metrics.append(("Phone", "N/A"))

        if mobile:
            metrics.append(("Mobile", f"tel:{mobile}"))
        else:
            metrics.append(("Mobile", "N/A"))

        metrics.extend(
            [
                ("Lifecycle", str(props.get("lifecyclestage") or "N/A")),
                ("Score", str(analysis.score)),
            ]
        )

        return UnifiedCard(
            title=name or email,
            subtitle=subtitle,
            emoji="👤",
            badge="FREE VERSION" if not is_pro else "PRO TIER",
            metrics=metrics,
            content=analysis.insight,
            secondary_content=[
                ("Next Best Action", analysis.next_best_action),
            ],
            actions=[
                CardAction(
                    label="Open in HubSpot",
                    action_type="url",
                    value="open_hubspot",
                    url=obj.get("hs_url", "https://app.hubspot.com"),
                ),
                CardAction(
                    label="View Deals",
                    action_type="callback",
                    value=f"view_contact_deals:{obj['id']}",
                ),
                CardAction(
                    label="View Meetings",
                    action_type="callback",
                    value=f"view_contact_meetings:{obj['id']}",
                ),
                CardAction(
                    label="Schedule Meeting",
                    action_type="modal",
                    value=f"schedule_meeting:{obj['id']}",
                ),
                CardAction(
                    label="View Company",
                    action_type="callback",
                    value=f"view_contact_company:{obj['id']}",
                ),
                CardAction(
                    label="Add Note",
                    action_type="modal",
                    value=f"add_note:contact:{obj['id']}",
                ),
            ],
        )

    def build_lead(
        self, obj: Mapping[str, Any], analysis: AIContactAnalysis, is_pro: bool = False
    ) -> UnifiedCard:
        """Builds a UnifiedCard representation for a HubSpot Lead."""
        props = obj["properties"]
        name = f"{props.get('firstname', '')} {props.get('lastname', '')}".strip()
        email = props.get("email", "unknown@example.com")

        return UnifiedCard(
            title=f"Lead: {name or email}",
            subtitle="Lead",
            emoji="🧲",
            badge="FREE VERSION" if not is_pro else "PRO TIER",
            metrics=[
                ("Email", email),
                ("Status", str(props.get("hs_lead_status") or "N/A")),
                ("Source", str(props.get("hs_analytics_source") or "N/A")),
                ("Score", str(analysis.score)),
            ],
            content=analysis.insight,
            secondary_content=[
                ("Next Best Action", analysis.next_best_action),
            ],
            actions=[
                CardAction(
                    label="Set Meeting Date",
                    action_type="modal",
                    value=f"schedule_meeting:{obj['id']}",
                ),
                CardAction(
                    label="Update Budget",
                    action_type="modal",
                    value=f"update_forecast_amount:{obj['id']}",
                ),
                CardAction(
                    label="Reassign Owner",
                    action_type="modal",
                    value=f"reassign_owner:contact:{obj['id']}",
                ),
            ],
        )

    def build_company(
        self,
        obj: Mapping[str, Any],
        analysis: AICompanyAnalysis,
        include_actions: bool = True,
        is_pro: bool = False,
    ) -> UnifiedCard:
        """Builds a UnifiedCard representation for a HubSpot Company.

        Args:
            obj (Mapping[str, Any]): Raw HubSpot company object.
            analysis (AICompanyAnalysis): Pre-calculated company health insights.
            include_actions (bool, optional): Whether to include action buttons.
                Defaults to True.
            is_pro (bool, optional): Whether the workspace is in the PRO tier.
                Defaults to False.

        Returns:
            UnifiedCard: The rendered IR for Slack or other platforms.

        """
        props = obj["properties"]
        name = props.get("name", "Unnamed Company")

        return UnifiedCard(
            title=name,
            subtitle="Company",
            emoji="🏢",
            badge="FREE VERSION" if not is_pro else "PRO TIER",
            metrics=[
                (
                    "Domain",
                    f"http://{props.get('domain')}" if props.get("domain") else "N/A",
                ),
                ("Industry", str(props.get("industry") or "N/A")),
                ("Size", str(props.get("numberofemployees") or "N/A")),
                ("Page Views", str(props.get("hs_analytics_num_page_views") or "0")),
                ("Sessions", str(props.get("hs_analytics_num_visits") or "0")),
                ("Health", analysis.health),
            ],
            content=analysis.summary,
            secondary_content=[
                ("Next Action", analysis.next_action),
            ],
            actions=[
                CardAction(
                    label="Open in HubSpot",
                    action_type="url",
                    value="open_hubspot",
                    url=obj.get("hs_url", "https://app.hubspot.com"),
                )
            ]
            + (
                [
                    CardAction(
                        label="View Deals",
                        action_type="callback",
                        value=f"view_company_deals:{obj['id']}",
                    ),
                    CardAction(
                        label="View Contacts",
                        action_type="callback",
                        value=f"view_contacts:{obj['id']}",
                    ),
                    CardAction(
                        label="Add Note",
                        action_type="modal",
                        value=f"add_note:company:{obj['id']}",
                    ),
                ]
                if include_actions
                else []
            ),
        )

    def build_deal(
        self,
        obj: Mapping[str, Any],
        analysis: AIDealAnalysis,
        pipelines: list[dict[str, Any]] | None = None,
        is_pro: bool = False,
    ) -> UnifiedCard:
        """Builds a UnifiedCard representation for a HubSpot Deal."""
        props = obj["properties"]
        name = props.get("dealname", "Unnamed Deal")
        current_stage_id = props.get("dealstage")
        pipeline_id = props.get("pipeline")

        # Resolve stage name and build options
        stage_label = "Unknown"
        pipeline_label = "Unknown"
        stage_options = []

        if pipelines and pipeline_id:
            pipeline = next((p for p in pipelines if p["id"] == pipeline_id), None)
            if pipeline:
                pipeline_label = pipeline.get("label", pipeline_id)
                for stage in pipeline.get("stages", []):
                    label = stage["label"]
                    if len(label) > 72:  # noqa: PLR2004
                        label = label[:72] + "..."
                    stage_id = stage["id"]
                    stage_options.append((label, stage_id))
                    if stage_id == current_stage_id:
                        stage_label = label
        elif current_stage_id:
            stage_label = str(current_stage_id)

        # Map emojis to stages
        stage_emojis = {
            "appointmentscheduled": "📅",
            "qualifiedtobuy": "✅",
            "presentationscheduled": "🖥️",
            "decisionmakerboughtin": "🤝",
            "contractsent": "📝",
            "closedwon": "🟢",
            "closedlost": "🔴",
            "discovery": "🔍",
            "negotiation": "🟡",
        }
        emoji_prefix = stage_emojis.get(stage_label.lower().replace(" ", ""), "🔹")
        display_stage = f"{emoji_prefix} {stage_label}"

        amount = props.get("amount") or 0

        actions = [
            CardAction(
                label="Open in HubSpot",
                action_type="url",
                value="open_hubspot",
                url=obj.get("hs_url", "https://app.hubspot.com"),
            ),
            CardAction(
                label="Add Note",
                action_type="modal",
                value=f"add_note:deal:{obj['id']}",
            ),
        ]

        if stage_options:
            actions.insert(
                0,
                CardAction(
                    label="Update Stage",
                    action_type="select",
                    value=f"update_deal_stage:{obj['id']}",
                    options=stage_options,
                ),
            )

        if is_pro:
            actions.extend(
                [
                    CardAction(
                        label="Update Lead Type",
                        action_type="modal",
                        value=f"update_lead_type:{obj['id']}",
                    ),
                    CardAction(
                        label="Calculator",
                        action_type="modal",
                        value=f"open_calculator:{obj['id']}",
                    ),
                    CardAction(
                        label="Reassign Owner",
                        action_type="modal",
                        value=f"reassign_owner:deal:{obj['id']}",
                    ),
                    CardAction(
                        label="Schedule Meeting",
                        action_type="modal",
                        value=f"schedule_meeting:{obj['id']}",
                    ),
                ]
            )

        return UnifiedCard(
            title=name,
            subtitle="Deal",
            emoji="💰",
            badge="FREE VERSION" if not is_pro else "PRO TIER",
            metrics=[
                ("Pipeline", pipeline_label),
                ("Stage", display_stage),
                ("Amount", f"${float(amount):,.2f}"),
                ("Risk", str(getattr(analysis, "risk_score", "N/A"))),
            ],
            content=getattr(analysis, "summary", "No summary available."),
            secondary_content=[
                ("Next Action", getattr(analysis, "next_action", "N/A")),
            ],
            actions=actions,
        )

    def build_ai_insights(self, analysis: AIContactAnalysis) -> UnifiedCard:
        return UnifiedCard(
            title="AI Insights",
            subtitle="Contact Insights",
            emoji="🤖",
            content=analysis.summary,
            secondary_content=[
                ("Next Action", analysis.next_action),
                ("Reasoning", analysis.next_action_reason),
            ],
        )

    def build_ai_scoring(self, analysis: AIContactAnalysis) -> UnifiedCard:
        return UnifiedCard(
            title="AI Score",
            subtitle="Scoring Analysis",
            emoji="📊",
            metrics=[
                ("Score", str(analysis.score)),
            ],
            content=analysis.score_reason,
        )

    def build_ai_next_best_action(self, analysis: AIContactAnalysis) -> UnifiedCard:
        return UnifiedCard(
            title="Next Best Action",
            subtitle="Recommendation",
            emoji="🎯",
            content=analysis.next_action,
            secondary_content=[
                ("Reasoning", analysis.next_action_reason),
            ],
        )

    def build_company_ai(self, analysis: AICompanyAnalysis) -> UnifiedCard:
        """Builds a UnifiedCard for Company-specific AI insights.

        Args:
            analysis (AICompanyAnalysis): The company AI analysis data.

        Returns:
            UnifiedCard: The rendered IR.

        """
        return UnifiedCard(
            title="Company Insights",
            emoji="🏢",
            content=analysis.summary,
            secondary_content=[
                ("Health", analysis.health),
                ("Next Action", analysis.next_action),
            ],
        )

    def build_deal_ai(self, analysis: AIDealAnalysis) -> UnifiedCard:
        """Builds a UnifiedCard for Deal-specific AI insights.

        Args:
            analysis (AIDealAnalysis): The deal AI analysis data.

        Returns:
            UnifiedCard: The rendered IR.

        """
        return UnifiedCard(
            title="Deal Insights",
            emoji="💰",
            content=analysis.summary,
            secondary_content=[
                ("Risk", analysis.risk),
                ("Next Action", analysis.next_action),
            ],
        )

    def build_ticket(
        self, obj: Mapping[str, Any], analysis: AITicketAnalysis, is_pro: bool = False
    ) -> UnifiedCard:
        """Builds a UnifiedCard representation for a HubSpot Ticket.

        Args:
            obj (Mapping[str, Any]): Raw HubSpot ticket object.
            analysis (AITicketAnalysis): Pre-calculated ticket urgency insights.
            is_pro (bool, optional): Whether the workspace is in the PRO tier.
                Defaults to False.

        Returns:
            UnifiedCard: The rendered IR for Slack or other platforms.

        """
        props = obj["properties"]
        subject = props.get("subject") or "Untitled Ticket"
        ticket_id = obj.get("id")

        return UnifiedCard(
            title=f"Ticket #{ticket_id}: {subject}",
            subtitle=f"Ticket • Stage: {props.get('hs_pipeline_stage', 'Unknown')}",
            emoji="🎫",
            badge="FREE VERSION" if not is_pro else "PRO TIER",
            metrics=[
                ("Priority", props.get("hs_ticket_priority") or "—"),
                ("Urgency", analysis.urgency),
            ],
            content=analysis.summary,
            secondary_content=[
                ("Next Action", analysis.next_action),
            ],
            actions=[
                CardAction(
                    label="Open in HubSpot",
                    action_type="url",
                    value="open_hubspot",
                    url=obj.get("hs_url", "https://app.hubspot.com"),
                ),
                CardAction(
                    label="Add Note",
                    action_type="modal",
                    value=f"add_note:ticket:{obj['id']}",
                ),
                CardAction(
                    label="AI Recap",
                    action_type="modal",
                    value=f"ai_recap:ticket:{obj['id']}",
                ),
            ],
        )

    def build_task(
        self,
        obj: Mapping[str, Any],
        analysis: AITaskAnalysis,
        context: dict[str, Any] | None = None,
        is_pro: bool = False,
    ) -> UnifiedCard:
        """Builds a UnifiedCard representation for a HubSpot Task.

        Args:
            obj (Mapping[str, Any]): Raw HubSpot task object.
            analysis (AITaskAnalysis): Pre-calculated task status insights.
            context (dict[str, Any] | None, optional): Enriched context
                (owner, associations). Defaults to None.
            is_pro (bool, optional): Whether the workspace is in the PRO tier.
                Defaults to False.

        Returns:
            UnifiedCard: The rendered IR for Slack or other platforms.

        """
        props = obj["properties"]
        subject = props.get("hs_task_subject") or "Untitled Task"
        status = props.get("hs_task_status", "Unknown")
        priority = props.get("hs_task_priority") or "—"
        task_type = props.get("hs_task_type") or "Task"

        # Format due date
        due_date = "No Due Date"
        ts = props.get("hs_timestamp")
        if ts:
            try:
                # HubSpot works in milliseconds
                dt = datetime.fromtimestamp(int(ts) / 1000)
                due_date = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                pass

        # Context fields
        owner_name = "Unassigned"
        contacts_str = "None"
        companies_str = "None"

        if context:
            owner_name = context.get("owner_name", "Unassigned")
            contacts = context.get("contacts", [])
            companies = context.get("companies", [])
            if contacts:
                contacts_str = ", ".join(contacts)
            if companies:
                companies_str = ", ".join(companies)

        return UnifiedCard(
            title=subject,
            subtitle=f"{task_type} • Status: {status}",
            emoji="✅",
            badge="FREE VERSION" if not is_pro else "PRO TIER",
            metrics=[
                ("Due", due_date),
                ("Priority", priority),
                ("Assigned To", owner_name),
                ("Status", analysis.status_label),
            ],
            content=self._strip_html(
                props.get("hs_task_body") or "No details provided."
            ),
            secondary_content=[
                ("Associated Contacts", contacts_str),
                ("Associated Companies", companies_str),
                ("Next Action", analysis.next_action),
            ],
            actions=[
                CardAction(
                    label="Open in HubSpot",
                    action_type="url",
                    value="open_hubspot",
                    url=obj.get("hs_url", "https://app.hubspot.com"),
                ),
                CardAction(
                    label="Add Note",
                    action_type="modal",
                    value=f"add_note:task:{obj['id']}",
                ),
            ],
        )

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

    def build_meeting_modal(self, contact_id: str, metadata: str | None = None) -> dict:
        """Builds the Slack Modal for scheduling a meeting in HubSpot."""
        return {
            "type": "modal",
            "callback_id": "schedule_meeting_modal",
            "private_metadata": metadata or contact_id,
            "title": {"type": "plain_text", "text": "Schedule Meeting"},
            "submit": {"type": "plain_text", "text": "Create"},
            "close": {"type": "plain_text", "text": "Cancel"},
            "blocks": [
                {
                    "type": "input",
                    "block_id": "title_block",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "title_input",
                        "placeholder": {"type": "plain_text", "text": "Meeting Title"},
                    },
                    "label": {"type": "plain_text", "text": "Title"},
                },
                {
                    "type": "input",
                    "block_id": "date_block",
                    "element": {
                        "type": "datepicker",
                        "action_id": "date_input",
                        "placeholder": {"type": "plain_text", "text": "Select date"},
                    },
                    "label": {"type": "plain_text", "text": "Date"},
                },
                {
                    "type": "input",
                    "block_id": "time_block",
                    "element": {
                        "type": "timepicker",
                        "action_id": "time_input",
                        "placeholder": {"type": "plain_text", "text": "Select time"},
                    },
                    "label": {"type": "plain_text", "text": "Time"},
                },
                {
                    "type": "input",
                    "block_id": "body_block",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "body_input",
                        "multiline": True,
                        "placeholder": {
                            "type": "plain_text",
                            "text": "What is this meeting about?",
                        },
                    },
                    "label": {"type": "plain_text", "text": "Description"},
                    "optional": True,
                },
            ],
        }

    def build_empty(self, message: str) -> UnifiedCard:
        return UnifiedCard(
            title="Notification",
            emoji="ℹ️",
            content=message,
        )

    def build_loading_modal(self, title: str = "Loading...") -> dict:
        """Builds a simple loading modal payload."""
        return {
            "type": "modal",
            "title": {"type": "plain_text", "text": title[:24]},
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "⏳ *Fetching data from HubSpot...* Please wait.",
                    },
                }
            ],
        }

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

    def build_disambiguation(self, options: list[dict]) -> UnifiedCard:
        actions = []
        for o in options:
            name = (
                o["properties"].get("name")
                or o["properties"].get("dealname")
                or o["properties"].get("subject")
                or o["properties"].get("hs_task_subject")
                or "Unknown"
            )
            actions.append(
                CardAction(
                    label=f"Select {name}",
                    action_type="callback",
                    value=f"select:{o.get('type')}:{o['id']}",
                )
            )

        return UnifiedCard(
            title="Which one did you mean?",
            emoji="❓",
            actions=actions,
        )

    def build_conversation(
        self, obj: Mapping[str, Any], analysis: AIConversationAnalysis
    ) -> UnifiedCard:
        """Builds a UnifiedCard for a Conversation Thread."""
        t_id = obj.get("id")
        return UnifiedCard(
            title=f"Conversation #{t_id}",
            subtitle=f"Status: {analysis.status}",
            emoji="💬",
            content=analysis.summary,
            actions=[
                CardAction(
                    label="Reply in Inbox",
                    action_type="url",
                    value="reply",
                    url=f"https://app.hubspot.com/live-messages/{obj.get('portalId')}/inbox/{t_id}",
                )
            ],
        )

    def build(
        self,
        obj: Mapping[str, Any],
        analysis: AIContactAnalysis
        | AICompanyAnalysis
        | AIDealAnalysis
        | AITicketAnalysis
        | AITaskAnalysis
        | AIConversationAnalysis,
        pipelines: list[dict[str, Any]] | None = None,
        task_context: dict[str, Any] | None = None,
        is_pro: bool = False,
    ) -> UnifiedCard:
        """Description:
        Unified entry point for building any CRM object card as a UnifiedCard IR.
        """
        obj_type = str(obj.get("type", "")).lower()

        if obj_type == "deal":
            return self.build_deal(
                obj, cast(AIDealAnalysis, analysis), pipelines, is_pro=is_pro
            )

        if obj_type == "task":
            return self.build_task(obj, cast(AITaskAnalysis, analysis), task_context)

        # Dispatch registry
        registry = {
            "contact": self.build_contact,
            "lead": self.build_lead,
            "company": self.build_company,
            "ticket": self.build_ticket,
            "conversation": self.build_conversation,
            "thread": self.build_conversation,
        }

        builder = registry.get(obj_type)
        if builder:
            return builder(obj, cast(Any, analysis))

        # Legacy heuristics fallback
        return self._build_from_legacy_heuristics(obj, analysis)

    def _strip_html(self, text: str) -> str:
        """Remove HTML tags from text."""
        if not text:
            return ""
        # Remove tags
        clean = re.sub(r"<[^>]+>", "", text)
        # Restore logical newlines if implied by BR or P
        # (This simple regex just deletes tags. For better formatting,
        # replace <br> with \n before stripping)
        # Let's try to be slightly smarter: replace <br> and </p> with newlines first
        text_with_newlines = re.sub(r"(?i)<br\s*/?>", "\n", text)
        text_with_newlines = re.sub(r"(?i)</p>", "\n", text_with_newlines)
        clean = re.sub(r"<[^>]+>", "", text_with_newlines)
        return clean.strip()

    def _build_from_legacy_heuristics(
        self,
        obj: Mapping[str, Any],
        analysis: Any,
    ) -> UnifiedCard:
        props = obj.get("properties", {})

        if "dealname" in props:
            return self.build_deal(obj, cast(AIDealAnalysis, analysis))

        if "domain" in props:
            return self.build_company(obj, cast(AICompanyAnalysis, analysis))

        if "subject" in props:
            return self.build_ticket(obj, cast(AITicketAnalysis, analysis))

        if "hs_task_subject" in props:
            return self.build_task(obj, cast(AITaskAnalysis, analysis))

        lifecycle = (props.get("lifecyclestage") or "").lower()
        if lifecycle == "lead":
            return self.build_lead(obj, cast(AIContactAnalysis, analysis))

        return self.build_contact(obj, cast(AIContactAnalysis, analysis))

    def build_update_lead_type_modal(
        self, deal_id: str, current_value: str = "", metadata: str | None = None
    ) -> dict:
        """Builds the Slack Modal for updating a deal's Lead Type."""
        return {
            "type": "modal",
            "callback_id": "update_lead_type_modal",
            "private_metadata": metadata or deal_id,
            "title": {"type": "plain_text", "text": "Update Lead Type"},
            "submit": {"type": "plain_text", "text": "Update"},
            "close": {"type": "plain_text", "text": "Cancel"},
            "blocks": [
                {
                    "type": "input",
                    "block_id": "lead_type_block",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "lead_type_input",
                        "initial_value": current_value,
                        "placeholder": {
                            "type": "plain_text",
                            "text": "e.g. New Business, Renewal, etc.",
                        },
                    },
                    "label": {"type": "plain_text", "text": "Lead Type"},
                },
            ],
        }

    def build_note_modal(
        self, object_type: str, object_id: str, metadata: str | None = None
    ) -> dict:
        """Builds the Slack Modal for logging a note to HubSpot."""
        return {
            "type": "modal",
            "callback_id": "add_note_modal",
            "private_metadata": metadata or f"{object_type}:{object_id}",
            "title": {"type": "plain_text", "text": "Log a Note"},
            "submit": {"type": "plain_text", "text": "Save"},
            "close": {"type": "plain_text", "text": "Cancel"},
            "blocks": [
                {
                    "type": "input",
                    "block_id": "note_input",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "content",
                        "multiline": True,
                        "placeholder": {
                            "type": "plain_text",
                            "text": "What happened with this record?",
                        },
                    },
                    "label": {"type": "plain_text", "text": "Note Content"},
                }
            ],
        }

    def build_post_mortem_modal(
        self, deal_id: str, stage_id: str, metadata: str | None = None
    ) -> dict:
        """Builds the Win/Loss post-mortem modal."""
        is_won = "won" in stage_id.lower()
        title = "Closed Won Details" if is_won else "Closed Lost Details"

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "*Almost there!* Please provide details for this deal "
                        "status change."
                    ),
                },
            }
        ]

        if is_won:
            blocks.append(
                self._input(
                    "Closed Won Reason",
                    "closed_won_reason",
                    placeholder="What was the key factor in winning?",
                )
            )
        else:
            blocks.append(
                self._select(
                    "Closed Lost Reason",
                    "closed_lost_reason",
                    [
                        ("Price", "price"),
                        ("Product Fit", "product_fit"),
                        ("Lost to Competitor", "competitor"),
                        ("Project Shelved", "shelved"),
                    ],
                )
            )

        return {
            "type": "modal",
            "callback_id": "post_mortem_submission",
            "private_metadata": metadata or f"{deal_id}:{stage_id}",
            "title": {"type": "plain_text", "text": title},
            "submit": {"type": "plain_text", "text": "Save & Close"},
            "close": {"type": "plain_text", "text": "Cancel"},
            "blocks": blocks,
        }

    def build_pricing_calculator_modal(
        self, deal_id: str, current_amount: float = 0.0, metadata: str | None = None
    ) -> dict:
        """Builds the pricing calculator modal."""
        return {
            "type": "modal",
            "callback_id": "calculator_submission",
            "private_metadata": metadata or deal_id,
            "title": {"type": "plain_text", "text": "Deal Calculator"},
            "submit": {"type": "plain_text", "text": "Calculate & Update"},
            "close": {"type": "plain_text", "text": "Cancel"},
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"Current Amount: `${current_amount:,}`",
                    },
                },
                self._input("Quantity", "quantity", placeholder="10"),
                self._input("Unit Price", "unit_price", placeholder="100.00"),
                self._input("Discount %", "discount_percent", placeholder="15"),
            ],
        }

    def build_next_step_enforcement_modal(
        self, deal_id: str, stage_id: str, metadata: str | None = None
    ) -> dict:
        """Forces a Next Step input before stage change."""
        return {
            "type": "modal",
            "callback_id": "next_step_enforcement_submission",
            "private_metadata": metadata or f"{deal_id}:{stage_id}",
            "title": {"type": "plain_text", "text": "Next Step Required"},
            "submit": {"type": "plain_text", "text": "Update Status"},
            "close": {"type": "plain_text", "text": "Cancel"},
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            "📈 *Stage Change Enforcement*\nYour manager requires a "
                            "'Next Step' to be set before moving this deal forward."
                        ),
                    },
                },
                self._input(
                    "Next Step",
                    "next_step",
                    placeholder="e.g. Schedule final demo with CTO",
                ),
            ],
        }

    def build_reassign_modal(
        self, object_id: str, owners: list[dict], metadata: str | None = None
    ) -> dict:
        """Builds modal to reassign owner."""
        owner_options = [(o["email"], o["id"]) for o in owners[:100]]
        return {
            "type": "modal",
            "callback_id": "reassign_owner_submission",
            "private_metadata": metadata or object_id,
            "title": {"type": "plain_text", "text": "Reassign Owner"},
            "submit": {"type": "plain_text", "text": "Reassign"},
            "close": {"type": "plain_text", "text": "Cancel"},
            "blocks": [
                self._select("Select New Owner", "hubspot_owner_id", owner_options),
            ],
        }

    def build_ai_recap_modal(
        self,
        object_type: str,
        object_id: str,
        summary: AIThreadSummary,
        metadata: str | None = None,
    ) -> dict[str, Any]:
        """Builds the AI Recap review modal."""
        # Clean summary for Slack
        recap_text = summary.summary
        key_points_text = "\n".join([f"• {p}" for p in summary.key_points])

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*AI Recap for {object_type.capitalize()} #{object_id}*",
                },
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Summary:*\n{recap_text}"},
            },
        ]

        if key_points_text:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Key Points:*\n{key_points_text}",
                    },
                }
            )

        blocks.append(
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"Sentiment: *{summary.sentiment}*"}
                ],
            }
        )

        return {
            "type": "modal",
            "callback_id": "ai_recap_submission_modal",
            "private_metadata": metadata or f"{object_type}:{object_id}",
            "title": {"type": "plain_text", "text": "Review AI Recap"},
            "submit": {"type": "plain_text", "text": "Save to HubSpot"},
            "close": {"type": "plain_text", "text": "Cancel"},
            "blocks": blocks,
        }

    def _input(
        self,
        label: str,
        action_id: str,
        placeholder: str = "",
        initial_value: str = "",
        multiline: bool = False,
        optional: bool = False,
    ) -> dict[str, Any]:
        element: dict[str, Any] = {"type": "plain_text_input", "action_id": action_id}
        if placeholder:
            element["placeholder"] = {"type": "plain_text", "text": placeholder}
        if initial_value:
            element["initial_value"] = initial_value
        if multiline:
            element["multiline"] = True

        return {
            "type": "input",
            "block_id": f"block_{action_id}",
            "element": element,
            "label": {"type": "plain_text", "text": label},
            "optional": optional,
        }

    def _select(
        self,
        label: str,
        action_id: str,
        options: list[tuple[str, str]],
        initial_option: str | None = None,
        optional: bool = False,
    ) -> dict[str, Any]:
        select_options = [
            {"text": {"type": "plain_text", "text": lbl}, "value": val}
            for lbl, val in options
        ]

        element: dict[str, Any] = {
            "type": "static_select",
            "action_id": action_id,
            "options": select_options,
            "placeholder": {"type": "plain_text", "text": "Select..."},
        }

        if initial_option:
            opt_obj = next(
                (o for o in select_options if o["value"] == initial_option), None
            )
            if opt_obj:
                element["initial_option"] = opt_obj

        return {
            "type": "input",
            "block_id": f"block_{action_id}",
            "element": element,
            "label": {"type": "plain_text", "text": label},
            "optional": optional,
        }

    def _datepicker(
        self,
        label: str,
        action_id: str,
        initial_date: str | None = None,
        optional: bool = False,
    ) -> dict[str, Any]:
        element: dict[str, Any] = {
            "type": "datepicker",
            "action_id": action_id,
        }
        if initial_date:
            element["initial_date"] = initial_date

        return {
            "type": "input",
            "block_id": f"block_{action_id}",
            "element": element,
            "label": {"type": "plain_text", "text": label},
            "optional": optional,
        }


class ModalBuilder:
    """Builder for Slack Modals (Views)."""

    def build_type_selection(self, callback_id: str) -> dict[str, Any]:
        """Builds the initial modal to select the object type."""
        return {
            "type": "modal",
            "callback_id": callback_id,
            "title": {"type": "plain_text", "text": "Create HubSpot Record"},
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Select the type of record you want to create:",
                    },
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "static_select",
                            "action_id": "select_object_type",
                            "placeholder": {
                                "type": "plain_text",
                                "text": "Choose type...",
                            },
                            "options": [
                                {
                                    "text": {"type": "plain_text", "text": "Company"},
                                    "value": "company",
                                },
                                {
                                    "text": {"type": "plain_text", "text": "Contact"},
                                    "value": "contact",
                                },
                                {
                                    "text": {"type": "plain_text", "text": "Deal"},
                                    "value": "deal",
                                },
                                {
                                    "text": {"type": "plain_text", "text": "Task"},
                                    "value": "task",
                                },
                                {
                                    "text": {"type": "plain_text", "text": "Ticket"},
                                    "value": "ticket",
                                },
                            ],
                        }
                    ],
                },
            ],
            "close": {"type": "plain_text", "text": "Cancel"},
        }

    def build_creation_modal(  # noqa: PLR0912, PLR0915
        self,
        object_type: str,
        callback_id: str,
        pipelines: list[dict[str, Any]] | None = None,
        owners: list[dict[str, Any]] | None = None,
        metadata: str | None = None,
    ) -> dict[str, Any]:
        """Builds the creation form modal for the specified object type."""
        blocks = []

        # Title
        title_text = f"Create {object_type.capitalize()}"

        # --- Contact Fields ---
        if object_type == "contact":
            blocks.extend(
                [
                    self._input("Email", "email", placeholder="alice@example.com"),
                    self._input("First Name", "firstname"),
                    self._input("Last Name", "lastname"),
                    self._input("Job Title", "jobtitle", optional=True),
                    self._input("Phone", "phone", optional=True),
                ]
            )

        # --- Deal Fields ---
        elif object_type == "deal":
            blocks.append(self._input("Deal Name", "dealname"))

            # Pipeline/Stage
            if pipelines:
                # Default to first pipeline
                pipeline_options = [(p["label"], p["id"]) for p in pipelines]
                blocks.append(self._select("Pipeline", "pipeline", pipeline_options))

                # Stages for first pipeline (simplified for now, ideally dynamic)
                stages = pipelines[0].get("stages", [])
                stage_options = [(s["label"], s["id"]) for s in stages]
                if stage_options:
                    blocks.append(self._select("Stage", "dealstage", stage_options))
            else:
                blocks.append(self._input("Pipeline ID", "pipeline", optional=True))
                blocks.append(self._input("Stage ID", "dealstage", optional=True))

            blocks.append(
                self._input("Amount", "amount", placeholder="1000.00", optional=True)
            )
            blocks.append(self._datepicker("Close Date", "closedate"))

            if owners:
                owner_options = [(o["email"], o["id"]) for o in owners[:100]]
                blocks.append(
                    self._select(
                        "Deal Owner", "hubspot_owner_id", owner_options, optional=True
                    )
                )

        # --- Lead Fields ---
        elif object_type == "lead":
            blocks.extend(
                [
                    self._input("First Name", "firstname"),
                    self._input("Last Name", "lastname"),
                    self._input("Email", "email", placeholder="lead@example.com"),
                    self._select(
                        "Lead Source",
                        "hs_analytics_source",
                        [
                            ("Website", "DIRECT_TRAFFIC"),
                            ("LinkedIn", "SOCIAL_MEDIA"),
                            ("Referral", "REFERRALS"),
                            ("Other", "OTHER"),
                        ],
                        optional=True,
                    ),
                    self._select(
                        "Lead Status",
                        "hs_lead_status",
                        [
                            ("New", "NEW"),
                            ("Contacted", "OPEN"),
                            ("Qualified", "IN_PROGRESS"),
                            ("Unqualified", "UNQUALIFIED"),
                        ],
                        optional=True,
                    ),
                ]
            )

        # --- Company Fields ---
        elif object_type == "company":
            blocks.extend(
                [
                    self._input("Company Name", "name"),
                    self._input("Domain", "domain", placeholder="example.com"),
                    self._input("Industry", "industry", optional=True),
                    self._input(
                        "Company Size",
                        "numberofemployees",
                        placeholder="e.g. 500",
                        optional=True,
                    ),
                ]
            )

        # --- Task Fields ---
        elif object_type == "task":
            blocks.append(self._input("Subject", "hs_task_subject"))
            blocks.append(
                self._select(
                    "Type",
                    "hs_task_type",
                    [
                        ("To-Do", "TODO"),
                        ("Call", "CALL"),
                        ("Email", "EMAIL"),
                    ],
                )
            )
            blocks.append(
                self._select(
                    "Priority",
                    "hs_task_priority",
                    [
                        ("🔴 High", "HIGH"),
                        ("🟡 Medium", "MEDIUM"),
                        ("🔵 Low", "LOW"),
                    ],
                    initial_option="MEDIUM",
                )
            )
            blocks.append(self._datepicker("Due Date", "hs_task_due_date"))
            blocks.append(
                self._input(
                    "Description", "hs_task_body", multiline=True, optional=True
                )
            )

            # Killer Feature: Association Dropdown (External Select)
            blocks.append(
                {
                    "type": "input",
                    "block_id": "block_association",
                    "element": {
                        "type": "external_select",
                        "action_id": "association_search",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Link to Contact, Deal, or Company...",
                        },
                        "min_query_length": 3,
                    },
                    "label": {"type": "plain_text", "text": "Associate with Record"},
                    "optional": True,
                }
            )

            if owners:
                owner_options = [(o["email"], o["id"]) for o in owners[:100]]
                blocks.append(
                    self._select(
                        "Assigned To", "hubspot_owner_id", owner_options, optional=True
                    )
                )

        # --- Ticket Fields ---
        elif object_type == "ticket":
            blocks.append(
                self._input(
                    "Ticket Subject",
                    "subject",
                    placeholder="Short summary of the issue",
                )
            )
            blocks.append(
                self._input(
                    "Description",
                    "content",
                    placeholder="Describe your problem in detail...",
                    multiline=True,
                )
            )
            blocks.append(
                self._select(
                    "Category",
                    "hs_ticket_category",
                    [
                        ("Billing", "BILLING"),
                        ("Technical Support", "TECH_SUPPORT"),
                        ("Report a Player/User", "REPORT_USER"),
                    ],
                )
            )
            blocks.append(
                self._select(
                    "Priority Level",
                    "hs_ticket_priority",
                    [
                        ("🔴 High", "HIGH"),
                        ("🟡 Medium", "MEDIUM"),
                        ("🔵 Low", "LOW"),
                    ],
                    initial_option="MEDIUM",
                )
            )

            # Association (optional)
            blocks.append(
                {
                    "type": "input",
                    "block_id": "block_association",
                    "element": {
                        "type": "external_select",
                        "action_id": "association_search",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Link to Contact, Deal, or Company...",
                        },
                        "min_query_length": 3,
                    },
                    "label": {"type": "plain_text", "text": "Associate with Record"},
                    "optional": True,
                }
            )

            if pipelines:
                pipeline_options = [(p["label"], p["id"]) for p in pipelines]
                blocks.append(self._select("Pipeline", "hs_pipeline", pipeline_options))

                # Default to first pipeline's stages if available
                stages = pipelines[0].get("stages", [])
                stage_options = [(s["label"], s["id"]) for s in stages]
                if stage_options:
                    blocks.append(
                        self._select(
                            "Ticket Status", "hs_pipeline_stage", stage_options
                        )
                    )

            blocks.append(
                self._select(
                    "Source",
                    "source_type",
                    [
                        ("Chat", "CHAT"),
                        ("Email", "EMAIL"),
                        ("Form", "FORM"),
                    ],
                    initial_option="CHAT",
                )
            )

            if pipelines:
                pipeline_options = [(p["label"], p["id"]) for p in pipelines]
                blocks.append(self._select("Pipeline", "hs_pipeline", pipeline_options))

                # Default to first pipeline's stages if available
                stages = pipelines[0].get("stages", [])
                stage_options = [(s["label"], s["id"]) for s in stages]
                if stage_options:
                    blocks.append(
                        self._select(
                            "Ticket Status", "hs_pipeline_stage", stage_options
                        )
                    )

            blocks.append(
                self._select(
                    "Source",
                    "source_type",
                    [
                        ("Chat", "CHAT"),
                        ("Email", "EMAIL"),
                        ("Form", "FORM"),
                    ],
                    initial_option="CHAT",
                )
            )

        # --- Company Fields ---
        elif object_type == "company":
            blocks.append(
                self._input("Company Domain", "domain", placeholder="example.com")
            )
            blocks.append(self._input("Name", "name"))
            blocks.append(self._input("City", "city", optional=True))

        return {
            "type": "modal",
            "callback_id": f"{callback_id}:{object_type}",
            "private_metadata": metadata or "",
            "title": {"type": "plain_text", "text": title_text},
            "blocks": blocks,
            "submit": {"type": "plain_text", "text": "Create"},
            "close": {"type": "plain_text", "text": "Cancel"},
        }

    def _input(
        self,
        label: str,
        action_id: str,
        placeholder: str = "",
        initial_value: str = "",
        multiline: bool = False,
        optional: bool = False,
    ) -> dict[str, Any]:
        element: dict[str, Any] = {"type": "plain_text_input", "action_id": action_id}
        if placeholder:
            element["placeholder"] = {"type": "plain_text", "text": placeholder}
        if initial_value:
            element["initial_value"] = initial_value
        if multiline:
            element["multiline"] = True

        return {
            "type": "input",
            "block_id": f"block_{action_id}",
            "element": element,
            "label": {"type": "plain_text", "text": label},
            "optional": optional,
        }

    def _select(
        self,
        label: str,
        action_id: str,
        options: list[tuple[str, str]],
        initial_option: str | None = None,
        optional: bool = False,
    ) -> dict[str, Any]:
        select_options = [
            {"text": {"type": "plain_text", "text": lbl}, "value": val}
            for lbl, val in options
        ]

        element: dict[str, Any] = {
            "type": "static_select",
            "action_id": action_id,
            "options": select_options,
            "placeholder": {"type": "plain_text", "text": "Select..."},
        }

        if initial_option:
            # Find the option object
            opt_obj = next(
                (o for o in select_options if o["value"] == initial_option), None
            )
            if opt_obj:
                element["initial_option"] = opt_obj

        return {
            "type": "input",
            "block_id": f"block_{action_id}",
            "element": element,
            "label": {"type": "plain_text", "text": label},
            "optional": optional,
        }

    def _datepicker(
        self,
        label: str,
        action_id: str,
        initial_date: str | None = None,
        optional: bool = False,
    ) -> dict[str, Any]:
        element: dict[str, Any] = {
            "type": "datepicker",
            "action_id": action_id,
        }
        if initial_date:
            element["initial_date"] = initial_date

        return {
            "type": "input",
            "block_id": f"block_{action_id}",
            "element": element,
            "label": {"type": "plain_text", "text": label},
            "optional": optional,
        }

    def build_ticket_control_panel(
        self, ticket_id: str, subject: str
    ) -> list[dict[str, Any]]:
        """Constructs the Control Panel message for a new ticket channel."""
        return [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"🎫 *Ticket Control Panel*"
                        f"\n*ID:* {ticket_id}"
                        f"\n*Subject:* {subject}"
                        "\n\nUse the buttons below"
                        " to manage this ticket."
                    ),
                },
            },
            {"type": "divider"},
            {
                "type": "actions",
                "block_id": f"ticket_actions:{ticket_id}",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Close 🔒"},
                        "style": "primary",
                        "action_id": "ticket_close",
                        "value": ticket_id,
                        "confirm": {
                            "title": {"type": "plain_text", "text": "Are you sure?"},
                            "text": {
                                "type": "plain_text",
                                "text": (
                                    "This will close the ticket"
                                    " in HubSpot and archive"
                                    " this channel."
                                ),
                            },
                            "confirm": {"type": "plain_text", "text": "Close Ticket"},
                            "deny": {"type": "plain_text", "text": "Cancel"},
                        },
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Claim 🙋‍♂️"},
                        "action_id": "ticket_claim",
                        "value": ticket_id,
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Transcript 📄"},
                        "action_id": "ticket_transcript",
                        "value": ticket_id,
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Delete 🗑️"},
                        "style": "danger",
                        "action_id": "ticket_delete",
                        "value": ticket_id,
                        "confirm": {
                            "title": {"type": "plain_text", "text": "Permanent Action"},
                            "text": {
                                "type": "plain_text",
                                "text": (
                                    "This will permanently"
                                    " archive the channel."
                                    " Are you sure?"
                                ),
                            },
                            "confirm": {"type": "plain_text", "text": "Delete Channel"},
                            "deny": {"type": "plain_text", "text": "Cancel"},
                        },
                    },
                ],
            },
        ]
