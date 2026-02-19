from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from app.core.models.ui import CardAction, UnifiedCard
from app.domains.ai.service import (
    AICompanyAnalysis,
    AIContactAnalysis,
    AIDealAnalysis,
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
                ("Email", email),
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
                ("Domain", props.get("domain", "N/A")),
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
        self, obj: Mapping[str, Any], analysis: AIDealAnalysis
    ) -> UnifiedCard:
        """Builds a UnifiedCard representation for a HubSpot Deal.

        Args:
            obj (Mapping[str, Any]): Raw HubSpot deal object.
            analysis (AIDealAnalysis): Pre-calculated deal insights and risk assessment.

        Returns:
            UnifiedCard: The rendered IR.

        """
        props = obj["properties"]
        name = props.get("dealname", "Unnamed Deal")

        return UnifiedCard(
            title=name,
            subtitle=f"Deal • Stage: {props.get('dealstage', 'unknown')}",
            emoji="💰",
            metrics=[
                ("Amount", props.get("amount", "N/A")),
                ("Risk", analysis.risk),
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
                    value=f"add_note:deal:{obj['id']}",
                ),
            ],
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

        return UnifiedCard(
            title=subject,
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
        self, obj: Mapping[str, Any], analysis: AITaskAnalysis
    ) -> UnifiedCard:
        """Builds a UnifiedCard representation for a HubSpot Task.

        Args:
            obj (Mapping[str, Any]): Raw HubSpot task object.
            analysis (AITaskAnalysis): Pre-calculated task status insights.

        Returns:
            UnifiedCard: The rendered IR.

        """
        props = obj["properties"]
        subject = props.get("hs_task_subject") or "Untitled Task"

        return UnifiedCard(
            title=subject,
            subtitle=f"Task • Status: {props.get('hs_task_status', 'Unknown')}",
            emoji="✅",
            metrics=[
                ("Priority", props.get("hs_task_priority") or "—"),
                ("Status", analysis.status_label),
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
                    value=f"add_note:task:{obj['id']}",
                ),
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

    def build_empty(self, message: str) -> UnifiedCard:
        return UnifiedCard(
            title="Not Found",
            emoji="😕",
            content=message,
        )

    def build_search_results(self, results: list[dict]) -> UnifiedCard:
        if not results:
            return self.build_empty("No results found")

        actions = []
        for r in results:
            name = (
                r["properties"].get("name")
                or r["properties"].get("dealname")
                or r["properties"].get("subject")
                or r["properties"].get("hs_task_subject")
                or "Unknown"
            )
            actions.append(
                CardAction(
                    label=f"View {name}",
                    action_type="callback",
                    value=f"view:{r.get('type')}:{r['id']}",
                )
            )

        return UnifiedCard(
            title="Search Results",
            emoji="🔍",
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

    def build(
        self,
        obj: Mapping[str, Any],
        analysis: AIContactAnalysis
        | AICompanyAnalysis
        | AIDealAnalysis
        | AITicketAnalysis
        | AITaskAnalysis,
    ) -> UnifiedCard:
        """Description:
        Unified entry point for building any CRM object card as a UnifiedCard IR.
        """
        obj_type = str(obj.get("type", "")).lower()

        # Method dispatch table
        builders = {
            "contact": self.build_contact,
            "lead": self.build_lead,
            "company": self.build_company,
            "deal": self.build_deal,
            "ticket": self.build_ticket,
            "task": self.build_task,
        }

        builder = builders.get(obj_type)
        if builder:
            return builder(obj, cast(Any, analysis))

        # Legacy heuristics fallback
        # Legacy heuristics fallback
        return self._build_from_legacy_heuristics(obj, analysis)

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
