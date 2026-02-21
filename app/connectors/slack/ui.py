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
    AIKnowledgeAnalysis,
    AITaskAnalysis,
    AITicketAnalysis,
)


class CardBuilder:
    """Description:
        Unified utility for building platform-agnostic CRM and AI insight cards.

    Rules Applied:
        - Returns UnifiedCard IR.
        - Centralizes rendering logic for Contacts, Deals, Companies, Tickets,
          and Tasks.
    """

    def build_contact(
        self, obj: Mapping[str, Any], analysis: AIContactAnalysis
    ) -> UnifiedCard:
        """Builds a UnifiedCard representation for a HubSpot Contact.

        Args:
            obj (Mapping[str, Any]): Raw HubSpot contact object.
            analysis (AIContactAnalysis): Pre-calculated AI insights and scores.

        Returns:
            UnifiedCard: The rendered IR for Slack or other platforms.

        """
        props = obj["properties"]
        name = f"{props.get('firstname', '')} {props.get('lastname', '')}".strip()
        email = props.get("email", "unknown@example.com")

        return UnifiedCard(
            title=name or email,
            subtitle="Contact",
            emoji="👤",
            metrics=[
                ("Email", str(props.get("email") or "N/A")),
                ("Phone", str(props.get("phone") or "N/A")),
                ("Mobile", str(props.get("mobilephone") or "N/A")),
                ("Lifecycle", str(props.get("lifecyclestage") or "N/A")),
                ("Score", str(analysis.score)),
            ],
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
        self, obj: Mapping[str, Any], analysis: AIContactAnalysis
    ) -> UnifiedCard:
        """Builds a UnifiedCard representation for a HubSpot Lead.

        Args:
            obj (Mapping[str, Any]): Raw HubSpot lead object.
            analysis (AIContactAnalysis): Pre-calculated AI insights and scores.

        Returns:
            UnifiedCard: The rendered IR.

        """
        props = obj["properties"]
        name = f"{props.get('firstname', '')} {props.get('lastname', '')}".strip()
        email = props.get("email", "unknown@example.com")

        return UnifiedCard(
            title=f"Lead: {name or email}",
            subtitle="Lead",
            emoji="🧲",
            metrics=[
                ("Email", email),
                ("Score", str(analysis.score)),
            ],
            content=analysis.insight,
            secondary_content=[
                ("Next Best Action", analysis.next_best_action),
            ],
        )

    def build_company(
        self, obj: Mapping[str, Any], analysis: AICompanyAnalysis
    ) -> UnifiedCard:
        """Builds a UnifiedCard representation for a HubSpot Company.

        Args:
            obj (Mapping[str, Any]): Raw HubSpot company object.
            analysis (AICompanyAnalysis): Pre-calculated company health insights.

        Returns:
            UnifiedCard: The rendered IR.

        """
        props = obj["properties"]
        name = props.get("name", "Unnamed Company")

        return UnifiedCard(
            title=name,
            subtitle="Company",
            emoji="🏢",
            metrics=[
                ("Domain", str(props.get("domain") or "N/A")),
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
                ),
                CardAction(
                    label="View Deals",
                    action_type="callback",
                    value=f"view_deals:{obj['id']}",
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
            ],
        )

    def build_deal(
        self,
        obj: Mapping[str, Any],
        analysis: AIDealAnalysis,
        pipelines: list[dict[str, Any]] | None = None,
    ) -> UnifiedCard:
        """Builds a UnifiedCard representation for a HubSpot Deal.

        Args:
            obj (Mapping[str, Any]): Raw HubSpot deal object.
            analysis (AIDealAnalysis): Pre-calculated deal insights and risk assessment.
            pipelines (list[dict[str, Any]] | None): All deal pipelines/stages.

        Returns:
            UnifiedCard: The rendered IR.

        """
        props = obj["properties"]
        name = props.get("dealname", "Unnamed Deal")
        current_stage_id = props.get("dealstage")
        pipeline_id = props.get("pipeline")

        # Resolve stage name and build options
        stage_label = "Unknown"
        pipeline_label = "Unknown"
        stage_options = []

        if pipelines and pipeline_id:
            # Find the correct pipeline
            pipeline = next((p for p in pipelines if p["id"] == pipeline_id), None)
            if pipeline:
                pipeline_label = pipeline.get("label", pipeline_id)
                # Build options from stages
                for stage in pipeline.get("stages", []):
                    label = stage["label"]
                    # Truncate label to 75 chars for Slack
                    if len(label) > 75:  # noqa: PLR2004
                        label = label[:72] + "..."
                    stage_id = stage["id"]
                    stage_options.append((label, stage_id))
                    if stage_id == current_stage_id:
                        stage_label = label
        elif current_stage_id:
            # Fallback if no pipeline data available
            stage_label = current_stage_id

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

        # Add stage selector if we have options
        if stage_options:
            actions.insert(
                0,
                CardAction(
                    label="Update Stage",
                    action_type="select",
                    value=f"update_deal_stage:{obj['id']}",
                    options=stage_options,
                    # selected_option=current_stage_id,
                    # User wants placeholder "Update Stage" to show
                ),
            )

        return UnifiedCard(
            title=name,
            subtitle=f"Deal • Stage: {stage_label}",
            emoji="💰",
            metrics=[
                ("Pipeline", pipeline_label),
                ("Amount", str(props.get("amount") or "N/A")),
                ("Risk", analysis.risk),
            ],
            content=analysis.summary,
            secondary_content=[
                ("Next Action", analysis.next_action),
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
        self, obj: Mapping[str, Any], analysis: AITicketAnalysis
    ) -> UnifiedCard:
        """Builds a UnifiedCard representation for a HubSpot Ticket.

        Args:
            obj (Mapping[str, Any]): Raw HubSpot ticket object.
            analysis (AITicketAnalysis): Pre-calculated ticket urgency insights.

        Returns:
            UnifiedCard: The rendered IR.

        """
        props = obj["properties"]
        subject = props.get("subject") or "Untitled Ticket"
        ticket_id = obj.get("id")

        return UnifiedCard(
            title=f"Ticket #{ticket_id}: {subject}",
            subtitle=f"Ticket • Stage: {props.get('hs_pipeline_stage', 'Unknown')}",
            emoji="🎫",
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
            ],
        )

    def build_task(
        self,
        obj: Mapping[str, Any],
        analysis: AITaskAnalysis,
        context: dict[str, Any] | None = None,
    ) -> UnifiedCard:
        """Builds a UnifiedCard representation for a HubSpot Task.

        Args:
            obj (Mapping[str, Any]): Raw HubSpot task object.
            analysis (AITaskAnalysis): Pre-calculated task status insights.
            context (dict[str, Any] | None): Enriched context (owner, associations).

        Returns:
            UnifiedCard: The rendered IR.

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

    def build_knowledge_article(
        self, obj: Mapping[str, Any], analysis: AIKnowledgeAnalysis
    ) -> UnifiedCard:
        """Builds a UnifiedCard for a Knowledge Base Article."""
        # obj is from content search API
        title = obj.get("title") or obj.get("name") or "Untitled Article"
        # Content search often returns 'url' or 'absoluteUrl'
        url = obj.get("url") or obj.get("absoluteUrl") or "https://app.hubspot.com"
        snippet = self._strip_html(
            obj.get("description") or obj.get("searchDescription") or ""
        )

        return UnifiedCard(
            title=title,
            subtitle="Knowledge Base Article",
            emoji="📚",
            metrics=[
                ("Relevance", analysis.relevance),
            ],
            content=snippet,
            actions=[
                CardAction(
                    label="Read Article",
                    action_type="url",
                    value="open_article",
                    url=url,
                )
            ],
        )

    def build_deals_list(self, deals: list[dict]) -> UnifiedCard:
        """Build a card showing a list of associated deals."""
        content_parts = []
        for deal in deals:
            props = deal.get("properties", {})
            name = props.get("dealname") or "Unnamed Deal"
            amount = props.get("amount") or "N/A"
            stage = props.get("dealstage") or "unknown"
            content_parts.append(f"*{name}*\nAmount: `{amount}` • Stage: `{stage}`")

        return UnifiedCard(
            title="Associated Deals",
            emoji="💰",
            content="\n\n".join(content_parts) if content_parts else "No deals found.",
        )

    def build_contacts_list(self, contacts: list[dict]) -> UnifiedCard:
        """Build a card showing a list of associated contacts."""
        content_parts = []
        for contact in contacts:
            props = contact.get("properties", {})
            name = f"{props.get('firstname', '')} {props.get('lastname', '')}".strip()
            email = props.get("email") or "N/A"
            lifecycle = props.get("lifecyclestage") or "—"
            content_parts.append(
                f"*{name or email}*\nEmail: `{email}` • Stage: `{lifecycle}`"
            )

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
        for meeting in meetings:
            props = meeting.get("properties", {})
            title = props.get("hs_meeting_title") or "Untitled Meeting"

            # Start time
            start_ts = props.get("hs_meeting_start_time")
            start_str = "No time set"
            if start_ts:
                try:
                    dt = datetime.fromtimestamp(int(start_ts) / 1000)
                    start_str = dt.strftime("%Y-%m-%d %H:%M")
                except (ValueError, TypeError):
                    pass

            outcome = props.get("hs_meeting_outcome", "No outcome")
            content_parts.append(
                f"📅 *{title}*\nTime: `{start_str}` • Outcome: `{outcome}`"
            )

        return UnifiedCard(
            title="Associated Meetings",
            emoji="📅",
            content="\n\n".join(content_parts)
            if content_parts
            else "No meetings found.",
        )

    def build_meeting_modal(self, contact_id: str) -> dict:
        """Builds the Slack Modal for scheduling a meeting in HubSpot."""
        return {
            "type": "modal",
            "callback_id": "schedule_meeting_modal",
            "private_metadata": contact_id,
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
            title="Not Found",
            emoji="😕",
            content=message,
        )

    def build_search_results(self, results: list[dict]) -> UnifiedCard:
        if not results:
            return self.build_empty("No results found")

        count = len(results)
        actions = []
        for r in results:
            props = r.get("properties", {})
            name = (
                props.get("name")
                or props.get("dealname")
                or props.get("subject")
                or props.get("hs_task_subject")
                or "Unknown"
            )

            # Add distinguishing detail so users can tell similar names apart
            detail = (
                props.get("domain")
                or props.get("email")
                or props.get("dealstage")
                or props.get("hs_pipeline_stage")
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
        | AIKnowledgeAnalysis
        | AIConversationAnalysis,
        pipelines: list[dict[str, Any]] | None = None,
        task_context: dict[str, Any] | None = None,
    ) -> UnifiedCard:
        """Description:
        Unified entry point for building any CRM object card as a UnifiedCard IR.
        """
        obj_type = str(obj.get("type", "")).lower()

        if obj_type == "deal":
            return self.build_deal(obj, cast(AIDealAnalysis, analysis), pipelines)

        if obj_type == "task":
            return self.build_task(obj, cast(AITaskAnalysis, analysis), task_context)

        if obj_type in ("knowledge_article", "knowledge"):
            return self.build_knowledge_article(
                obj, cast(AIKnowledgeAnalysis, analysis)
            )

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

    def build_note_modal(self, object_type: str, object_id: str) -> dict:
        """Builds the Slack Modal for logging a note to HubSpot."""
        return {
            "type": "modal",
            "callback_id": "add_note_modal",
            "private_metadata": f"{object_type}:{object_id}",
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
                                {
                                    "text": {"type": "plain_text", "text": "Company"},
                                    "value": "company",
                                },
                            ],
                        }
                    ],
                },
            ],
            "close": {"type": "plain_text", "text": "Cancel"},
        }

    def build_creation_modal(
        self,
        object_type: str,
        callback_id: str,
        pipelines: list[dict[str, Any]] | None = None,
        owners: list[dict[str, Any]] | None = None,
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
                owner_options = [
                    (o["email"], o["id"]) for o in owners[:100]
                ]  # Limit 100
                blocks.append(
                    self._select(
                        "Deal Owner", "hubspot_owner_id", owner_options, optional=True
                    )
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
                self._datepicker("Due Date", "hs_task_due_date")
            )  # Note: API expects timestamp
            blocks.append(
                self._select(
                    "Priority",
                    "hs_task_priority",
                    [
                        ("High", "HIGH"),
                        ("Medium", "MEDIUM"),
                        ("Low", "LOW"),
                    ],
                    initial_option="MEDIUM",
                )
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
            blocks.append(self._input("Ticket Name", "subject"))
            blocks.append(
                self._select(
                    "Priority",
                    "hs_ticket_priority",
                    [
                        ("High", "HIGH"),
                        ("Medium", "MEDIUM"),
                        ("Low", "LOW"),
                    ],
                    initial_option="MEDIUM",
                )
            )

            if pipelines:
                # Assuming Ticket pipeline is passed similarly, or uses default
                # For simplicity, fallback to inputs if no pipeline structure
                # passed specifically for tickets
                pass

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
            blocks.append(self._input("Industry", "industry", optional=True))

        return {
            "type": "modal",
            "callback_id": f"{callback_id}:{object_type}",
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
