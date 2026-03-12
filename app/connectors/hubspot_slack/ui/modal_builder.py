from __future__ import annotations

from typing import Any

from app.domains.crm.ui.mixins.components import ComponentsMixin

MAX_LIST_DISPLAY = 25
MAX_OWNERS_DISPLAY = 100


class ModalBuilder(ComponentsMixin):
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
