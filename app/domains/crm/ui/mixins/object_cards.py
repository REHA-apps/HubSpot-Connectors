from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, cast

from app.core.models.ui import CardAction, UnifiedCard
from app.domains.ai.service import (
    AIAppointmentAnalysis,
    AICommunicationAnalysis,
    AICompanyAnalysis,
    AIContactAnalysis,
    AIConversationAnalysis,
    AIDealAnalysis,
    AIEngagementAnalysis,
    AITaskAnalysis,
    AITicketAnalysis,
)

from .components import ComponentsMixin

MAX_LIST_DISPLAY = 25
MAX_OWNERS_DISPLAY = 100


class ObjectCardsMixin(ComponentsMixin):
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
                    is_gated=not is_pro,
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
                    is_gated=not is_pro,
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
                    is_gated=not is_pro,
                ),
                CardAction(
                    label="Update Budget",
                    action_type="modal",
                    value=f"update_forecast_amount:{obj['id']}",
                    is_gated=not is_pro,
                ),
                CardAction(
                    label="Reassign Owner",
                    action_type="modal",
                    value=f"reassign_owner:contact:{obj['id']}",
                    is_gated=not is_pro,
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
            actions=(
                [
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
                            is_gated=not is_pro,
                        ),
                    ]
                    if include_actions
                    else []
                )
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

        if True:  # Changed from if is_pro to always include, but gated
            actions.extend(
                [
                    CardAction(
                        label="Update Lead Type",
                        action_type="modal",
                        value=f"update_lead_type:{obj['id']}",
                        is_gated=not is_pro,
                    ),
                    CardAction(
                        label="Calculator",
                        action_type="modal",
                        value=f"open_calculator:{obj['id']}",
                        is_gated=not is_pro,
                    ),
                    CardAction(
                        label="Reassign Owner",
                        action_type="modal",
                        value=f"reassign_owner:deal:{obj['id']}",
                        is_gated=not is_pro,
                    ),
                    CardAction(
                        label="Schedule Meeting",
                        action_type="modal",
                        value=f"schedule_meeting:{obj['id']}",
                        is_gated=not is_pro,
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
                    is_gated=not is_pro,
                ),
                CardAction(
                    label="AI Recap",
                    action_type="modal",
                    value=f"ai_recap:ticket:{obj['id']}",
                    is_gated=not is_pro,
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
        # contacts_str = "None" # Removed as per instruction
        # companies_str = "None" # Removed as per instruction

        if context:
            owner_name = context.get("owner_name", "Unassigned")
            contacts = context.get("contacts", [])
            companies = context.get("companies", [])
            if contacts:
                ", ".join(contacts)
            if companies:
                ", ".join(companies)

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
                    is_gated=not is_pro,
                ),
            ],
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

    def build_communication(
        self, obj: Mapping[str, Any], analysis: AICommunicationAnalysis
    ) -> UnifiedCard:
        """Builds a UnifiedCard for a HubSpot comm (SMS/WhatsApp/FB Messenger)."""
        props = obj.get("properties") or {}
        channel = analysis.channel
        return UnifiedCard(
            title=f"{channel} Message",
            subtitle=f"Communication • {channel}",
            emoji="💬",
            metrics=[
                ("Channel", channel),
                ("Direction", str(props.get("hs_communication_logged_from") or "N/A")),
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
            ],
        )

    def build_appointment(
        self,
        obj: Mapping[str, Any],
        analysis: AIAppointmentAnalysis,
        is_pro: bool = False,
    ) -> UnifiedCard:
        """Builds a UnifiedCard for a HubSpot Appointment."""
        props = obj.get("properties") or {}
        name = props.get("hs_appointment_name") or "Appointment"
        start = props.get("hs_appointment_start_time", "N/A")
        end = props.get("hs_appointment_end_time", "N/A")
        return UnifiedCard(
            title=name,
            subtitle=f"Appointment • {analysis.status_label}",
            emoji="📅",
            badge="FREE VERSION" if not is_pro else "PRO TIER",
            metrics=[
                ("Status", analysis.status_label),
                ("Start", str(start)[:16] if start != "N/A" else "N/A"),
                ("End", str(end)[:16] if end != "N/A" else "N/A"),
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
                    value=f"add_note:appointment:{obj.get('id')}",
                    is_gated=not is_pro,
                ),
            ],
        )

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

    def build(
        self,
        obj: Mapping[str, Any],
        analysis: AIContactAnalysis
        | AICompanyAnalysis
        | AIDealAnalysis
        | AITicketAnalysis
        | AITaskAnalysis
        | AIConversationAnalysis
        | AIEngagementAnalysis,
        pipelines: list[dict[str, Any]] | None = None,
        task_context: dict[str, Any] | None = None,
        *,
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
            "0-136": self.build_lead,
            "company": self.build_company,
            "ticket": self.build_ticket,
            "conversation": self.build_conversation,
            "thread": self.build_conversation,
            "communication": self.build_communication,
            "0-18": self.build_communication,
            "appointment": self.build_appointment,
            "0-421": self.build_appointment,
        }

        builder = registry.get(obj_type)
        if builder:
            # Propagate is_pro to builder functions
            import inspect

            sig = inspect.signature(builder)
            if "is_pro" in sig.parameters:
                return builder(obj, cast(Any, analysis), is_pro=is_pro)
            return builder(obj, cast(Any, analysis))

        # Legacy heuristics fallback
        return self._build_from_legacy_heuristics(obj, analysis)
