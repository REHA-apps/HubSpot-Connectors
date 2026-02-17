# app/slack/card_builder.py
from __future__ import annotations

from typing import Any, Mapping, Union, cast

from app.integrations.ai_service import (
    AIContactAnalysis,
    AICompanyAnalysis,
    AIDealAnalysis,
)


class CardBuilder:
    """Unified Slack CRM + AI card builder."""

    # ---------------------------------------------------------
    # Shared helpers
    # ---------------------------------------------------------

    @staticmethod
    def header(text: str, emoji: str = "") -> dict:
        prefix = f"{emoji} " if emoji else ""
        return {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{prefix}{text}", "emoji": True},
        }

    @staticmethod
    def markdown(text: str) -> dict:
        return {"type": "section", "text": {"type": "mrkdwn", "text": text}}

    @staticmethod
    def fields(fields: list[tuple[str, str]]) -> dict:
        return {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*{label}:*\n{value}"}
                for label, value in fields
            ],
        }

    @staticmethod
    def context(text: str) -> dict:
        return {"type": "context", "elements": [{"type": "mrkdwn", "text": text}]}

    @staticmethod
    def footer() -> dict:
        return CardBuilder.context("Powered by *HubSpot CRM Search*")

    @staticmethod
    def actions(buttons: list[dict]) -> dict:
        return {"type": "actions", "elements": buttons}

    # ---------------------------------------------------------
    # CRM OBJECT CARDS
    # ---------------------------------------------------------

    def build_contact(self, obj: Mapping[str, Any], analysis: AIContactAnalysis) -> dict:
        props = obj["properties"]
        name = f"{props.get('firstname', '')} {props.get('lastname', '')}".strip()
        email = props.get("email", "unknown@example.com")

        return {
            "blocks": [
                self.header(name or email, "👤"),
                self.context("*Contact*"),
                self.fields(
                    [
                        ("Email", f"<mailto:{email}|{email}>"),
                        ("Score", str(analysis.score)),
                    ]
                ),
                self.markdown(analysis.insight),
                self.markdown(f"*Next Best Action:* {analysis.next_best_action}"),
                self.actions(
                    [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Open in HubSpot"},
                            "url": obj.get("hs_url", "#"),
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Add Note"},
                            "value": f"add_note:{obj['id']}",
                            "action_id": "open_add_note_modal",
                        },
                    ]
                ),
                self.footer(),
            ]
        }

    def build_lead(self, obj: Mapping[str, Any], analysis: AIContactAnalysis) -> dict:
        props = obj["properties"]
        name = f"{props.get('firstname', '')} {props.get('lastname', '')}".strip()
        email = props.get("email", "unknown@example.com")

        return {
            "blocks": [
                self.header(f"Lead: {name or email}", "🧲"),
                self.fields(
                    [
                        ("Email", f"<mailto:{email}|{email}>"),
                        ("Score", str(analysis.score)),
                    ]
                ),
                self.markdown(analysis.insight),
                self.markdown(f"*Next Best Action:* {analysis.next_best_action}"),
                self.footer(),
            ]
        }

    def build_company(self, obj: Mapping[str, Any], analysis: AICompanyAnalysis) -> dict:
        props = obj["properties"]
        name = props.get("name", "Unnamed Company")

        return {
            "blocks": [
                self.header(name, "🏢"),
                self.context("*Company*"),
                self.fields(
                    [
                        ("Domain", props.get("domain", "N/A")),
                        ("Health", analysis.health),
                    ]
                ),
                self.markdown(analysis.summary),
                self.markdown(f"*Next Action:* {analysis.next_action}"),
                self.actions(
                    [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Open in HubSpot"},
                            "url": obj.get("hs_url", "#"),
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "View Deals"},
                            "value": f"view_deals:{obj['id']}",
                            "action_id": "view_deals",
                        },
                    ]
                ),
                self.footer(),
            ]
        }

    def build_deal(self, obj: Mapping[str, Any], analysis: AIDealAnalysis) -> dict:
        props = obj["properties"]
        name = props.get("dealname", "Unnamed Deal")

        return {
            "blocks": [
                self.header(name, "💰"),
                self.context(f"*Deal* • Stage: `{props.get('dealstage', 'unknown')}`"),
                self.fields(
                    [
                        ("Amount", props.get("amount", "N/A")),
                        ("Risk", analysis.risk),
                    ]
                ),
                self.markdown(analysis.summary),
                self.markdown(f"*Next Action:* {analysis.next_action}"),
                self.actions(
                    [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Open in HubSpot"},
                            "url": obj.get("hs_url", "#"),
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Add Note"},
                            "value": f"add_note:{obj['id']}",
                            "action_id": "open_add_note_modal",
                        },
                    ]
                ),
                self.footer(),
            ]
        }

    # ---------------------------------------------------------
    # AI‑ONLY CARDS
    # ---------------------------------------------------------

    def build_ai_insights(self, analysis: AIContactAnalysis) -> dict:
        return {
            "blocks": [
                self.header("AI Insights", "🤖"),
                self.markdown(f"*Summary*\n{analysis.summary}"),
                self.markdown(f"*Next Action*\n{analysis.next_action}"),
                self.context(f"*Reasoning:* {analysis.next_action_reason}"),
            ]
        }

    def build_ai_scoring(self, analysis: AIContactAnalysis) -> dict:
        return {
            "blocks": [
                self.header("AI Score", "📊"),
                self.markdown(f"*Score:* {analysis.score}\n*Why:* {analysis.score_reason}"),
            ]
        }

    def build_ai_next_best_action(self, analysis: AIContactAnalysis) -> dict:
        return {
            "blocks": [
                self.header("Next Best Action", "🎯"),
                self.markdown(f"*Recommended Action*\n{analysis.next_action}"),
                self.context(f"*Reasoning:* {analysis.next_action_reason}"),
            ]
        }

    def build_company_ai(self, analysis: AICompanyAnalysis) -> dict:
        return {
            "blocks": [
                self.header("Company Insights", "🏢"),
                self.markdown(f"*Summary*\n{analysis.summary}"),
                self.markdown(f"*Next Action*\n{analysis.next_action}"),
                self.context(f"*Health:* {analysis.health}"),
            ]
        }

    def build_deal_ai(self, analysis: AIDealAnalysis) -> dict:
        return {
            "blocks": [
                self.header("Deal Insights", "💰"),
                self.markdown(f"*Summary*\n{analysis.summary}"),
                self.markdown(f"*Next Action*\n{analysis.next_action}"),
                self.context(f"*Risk:* {analysis.risk}"),
            ]
        }

    # ---------------------------------------------------------
    # Utility Cards
    # ---------------------------------------------------------

    def build_empty(self, message: str) -> dict:
        return {"blocks": [self.markdown(f"😕 {message}")]}

    def build_search_results(self, results: list[dict]) -> dict:
        if not results:
            return self.build_empty("No results found")

        blocks = [self.header("Search Results", "🔍")]

        for r in results:
            name = (
                r["properties"].get("name")
                or r["properties"].get("dealname")
                or "Unknown"
            )
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*{name}*"},
                    "accessory": {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "View"},
                        "value": f"view:{r['id']}",
                        "action_id": "view_object",
                    },
                }
            )

        return {"blocks": blocks}

    def build_disambiguation(self, options: list[dict]) -> dict:
        blocks = [self.header("Which one did you mean", "❓")]

        for o in options:
            name = (
                o["properties"].get("name")
                or o["properties"].get("dealname")
                or "Unknown"
            )
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*{name}*"},
                    "accessory": {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Select"},
                        "value": f"select:{o['id']}",
                        "action_id": "select_object",
                    },
                }
            )

        return {"blocks": blocks}

    # ---------------------------------------------------------
    # Unified entry point for CRM objects
    # ---------------------------------------------------------

    def build(
        self,
        obj: Mapping[str, Any],
        analysis: Union[AIContactAnalysis, AICompanyAnalysis, AIDealAnalysis],
    ) -> dict:

        props = obj.get("properties", {})

        if "dealname" in props:
            return self.build_deal(obj, cast(AIDealAnalysis, analysis))

        if "domain" in props:
            return self.build_company(obj, cast(AICompanyAnalysis, analysis))

        lifecycle = (props.get("lifecyclestage") or "").lower()
        if lifecycle == "lead":
            return self.build_lead(obj, cast(AIContactAnalysis, analysis))

        return self.build_contact(obj, cast(AIContactAnalysis, analysis))