# app/integrations/ai_service.py
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.core.logging import CorrelationAdapter, get_logger
from app.utils.parsers import to_int

logger = get_logger("ai.service")


@dataclass(frozen=True)
class AIContactAnalysis:
    insight: str
    score: int
    next_best_action: str


class AIService:
    """Lightweight deterministic AI heuristics."""

    def __init__(self):
        self.log = logger  # plain logger

    def set_corr_id(self, corr_id: str):
        self.log = CorrelationAdapter(logger, corr_id)

    # ---------------------------------------------------------
    # Normalization
    # ---------------------------------------------------------
    def normalize_contact_props(self, props: dict[str, Any]) -> dict[str, Any]:
        numeric_fields = [
            "hs_analytics_num_visits",
            "num_associated_deals",
            "hs_lifecyclestage_lead_score",
        ]

        for field in numeric_fields:
            props[field] = to_int(props.get(field))

        return props

    # ---------------------------------------------------------
    # Insight generation
    # ---------------------------------------------------------
    def generate_contact_insight(self, contact: Mapping[str, Any]) -> str:
        props = self.normalize_contact_props(contact.get("properties", {}))

        firstname = props.get("firstname") or "This contact"
        company = props.get("company") or "Unknown Company"
        visits = props.get("hs_analytics_num_visits", 0)

        insight = f"💡 {firstname} works at {company}."

        if visits > 5:  # noqa: PLR2004
            insight += f" They are highly engaged with {visits} visits."
        else:
            insight += " Engagement is low."

        return insight

    # ---------------------------------------------------------
    # Scoring
    # ---------------------------------------------------------
    def generate_score(self, props: Mapping[str, Any]) -> int:
        props = self.normalize_contact_props(dict(props))

        score = 0

        visits = props.get("hs_analytics_num_visits", 0)
        if visits > 10:  # noqa: PLR2004
            score += 40

        if props.get("lifecyclestage") in {
            "marketingqualifiedlead",
            "salesqualifiedlead",
        }:
            score += 30

        if props.get("company"):
            score += 10

        if props.get("email"):
            score += 10

        return min(score, 100)

    # ---------------------------------------------------------
    # Next-best-action
    # ---------------------------------------------------------
    def next_best_action(self, props: Mapping[str, Any]) -> str:
        props = self.normalize_contact_props(dict(props))

        visits = props.get("hs_analytics_num_visits", 0)
        lifecycle = props.get("lifecyclestage")

        if lifecycle == "lead" and visits > 5:  # noqa: PLR2004
            return "📞 Reach out — this lead is warming up."

        if lifecycle == "marketingqualifiedlead":
            return "🤝 Hand off to sales — strong MQL."

        if lifecycle == "salesqualifiedlead":
            return "📅 Schedule a discovery call."

        if visits > 15:  # noqa: PLR2004
            return "🔥 High engagement — follow up immediately."

        return "📝 Add a note or send a follow-up email."

    # ---------------------------------------------------------
    # Unified analysis
    # ---------------------------------------------------------
    def analyze_contact(self, contact: Mapping[str, Any]) -> AIContactAnalysis:
        props = contact.get("properties", {})
        props = self.normalize_contact_props(dict(props))

        return AIContactAnalysis(
            insight=self.generate_contact_insight(contact),
            score=self.generate_score(props),
            next_best_action=self.next_best_action(props),
        )

    # ---------------------------------------------------------
    # Summary
    # ---------------------------------------------------------
    def summarize_results(self, objects: Sequence[Mapping[str, Any]]) -> str:
        if not objects:
            return "No matching HubSpot records found."

        contacts = sum(1 for o in objects if "firstname" in o.get("properties", {}))
        leads = sum(
            1
            for o in objects
            if o.get("properties", {}).get("lifecyclestage") == "lead"
        )
        deals = sum(1 for o in objects if "dealname" in o.get("properties", {}))

        parts = []
        if contacts:
            parts.append(f"{contacts} contact(s)")
        if leads:
            parts.append(f"{leads} lead(s)")
        if deals:
            parts.append(f"{deals} deal(s)")

        summary = " • ".join(parts)
        return f"🔎 *Summary:* Found {summary} matching your search."

    # ---------------------------------------------------------
    # Top recommended actions
    # ---------------------------------------------------------
    def top_recommended_actions(
        self,
        objects: Sequence[Mapping[str, Any]],
    ) -> list[str]:
        actions = []

        for obj in objects:
            props = self.normalize_contact_props(dict(obj.get("properties", {})))
            nba = self.next_best_action(props)
            score = self.generate_score(props)
            actions.append((score, nba))

        actions.sort(key=lambda x: x[0], reverse=True)

        seen = set()
        top = []
        for _, action in actions:
            if action not in seen:
                top.append(action)
                seen.add(action)
            if len(top) == 3:  # noqa: PLR2004
                break

        return top

    # ---------------------------------------------------------
    # Intent detection
    # ---------------------------------------------------------
    def detect_intent(self, query: str) -> str:
        q = query.lower()

        if any(k in q for k in ["deal", "renewal", "contract", "pipeline", "amount"]):
            return "deal"

        if any(k in q for k in ["lead", "mql", "sql", "prospect"]):
            return "lead"

        return "contact"
