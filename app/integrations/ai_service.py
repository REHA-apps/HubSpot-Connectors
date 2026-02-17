# app/integrations/ai_service.py
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.core.logging import CorrelationAdapter, get_logger
from app.utils.parsers import to_int

logger = get_logger("ai.service")


# ---------------------------------------------------------
# Dataclasses (immutable outputs)
# ---------------------------------------------------------
@dataclass(frozen=True)
class AIContactAnalysis:
    insight: str
    score: int
    score_reason: str
    next_best_action: str
    next_action: str
    next_action_reason: str
    summary: str
    reasoning: str


@dataclass(frozen=True)
class AICompanyAnalysis:
    summary: str
    health: str
    next_action: str


@dataclass(frozen=True)
class AIDealAnalysis:
    summary: str
    risk: str
    next_action: str


# ---------------------------------------------------------
# Contact AI Service
# ---------------------------------------------------------
class AIService:
    """Deterministic, explainable AI heuristics for HubSpot contacts."""

    def __init__(self) -> None:
        self.log = logger  # replaced via set_corr_id()

    def set_corr_id(self, corr_id: str) -> None:
        self.log = CorrelationAdapter(logger, corr_id)

    # -----------------------------------------------------
    # Normalization
    # -----------------------------------------------------
    def normalize_contact_props(self, props: dict[str, Any]) -> dict[str, Any]:
        """Normalize numeric fields and ensure consistent types."""
        numeric_fields = [
            "hs_analytics_num_visits",
            "num_associated_deals",
            "hs_lifecyclestage_lead_score",
        ]

        for field in numeric_fields:
            props[field] = to_int(props.get(field))

        return props

    # -----------------------------------------------------
    # Feature extraction
    # -----------------------------------------------------
    def _extract_features(self, props: Mapping[str, Any]) -> dict[str, Any]:
        """Extract normalized, typed features for scoring."""
        props = self.normalize_contact_props(dict(props))

        visits = props.get("hs_analytics_num_visits", 0)
        lifecycle = (props.get("lifecyclestage") or "").lower()
        company = props.get("company")
        email = props.get("email")

        return {
            "props": props,
            "visits": visits,
            "lifecycle": lifecycle,
            "has_company": bool(company),
            "has_email": bool(email),
        }

    # -----------------------------------------------------
    # Insight generation
    # -----------------------------------------------------
    def generate_contact_insight(self, contact: Mapping[str, Any]) -> str:
        props = self.normalize_contact_props(contact.get("properties", {}))

        firstname = props.get("firstname") or "This contact"
        company = props.get("company") or "Unknown Company"
        visits = props.get("hs_analytics_num_visits", 0)

        insight = f"💡 {firstname} works at {company}."

        if visits > 5:
            insight += f" They are highly engaged with {visits} visits."
        else:
            insight += " Engagement is low."

        return insight

    # -----------------------------------------------------
    # Scoring
    # -----------------------------------------------------
    def generate_score(self, props: Mapping[str, Any]) -> int:
        f = self._extract_features(props)
        score = 0

        if f["visits"] > 10:
            score += 40

        if f["lifecycle"] in {"marketingqualifiedlead", "salesqualifiedlead"}:
            score += 30

        if f["has_company"]:
            score += 10

        if f["has_email"]:
            score += 10

        return min(score, 100)

    def generate_score_reason(self, props: Mapping[str, Any], score: int) -> str:
        f = self._extract_features(props)
        reasons: list[str] = []

        if f["visits"] > 10:
            reasons.append("High engagement")
        elif f["visits"] > 5:
            reasons.append("Moderate engagement")
        else:
            reasons.append("Low engagement")

        if f["lifecycle"] in {"marketingqualifiedlead", "salesqualifiedlead"}:
            reasons.append("Qualified lifecycle stage")

        if f["has_company"]:
            reasons.append("Has company association")

        if f["has_email"]:
            reasons.append("Valid email present")

        return ", ".join(reasons) or "Low engagement"

    # -----------------------------------------------------
    # Next best action
    # -----------------------------------------------------
    def next_best_action(self, props: Mapping[str, Any]) -> str:
        f = self._extract_features(props)

        if f["lifecycle"] == "lead" and f["visits"] > 5:
            return "📞 Reach out — this lead is warming up."

        if f["lifecycle"] == "marketingqualifiedlead":
            return "🤝 Hand off to sales — strong MQL."

        if f["lifecycle"] == "salesqualifiedlead":
            return "📅 Schedule a discovery call."

        if f["visits"] > 15:
            return "🔥 High engagement — follow up immediately."

        return "📝 Add a note or send a follow-up email."

    def generate_next_action(self, props: Mapping[str, Any]) -> str:
        return self.next_best_action(props)

    def generate_next_action_reason(self, props: Mapping[str, Any]) -> str:
        f = self._extract_features(props)

        if f["lifecycle"] == "lead" and f["visits"] > 5:
            return "Lead is warming up"
        if f["lifecycle"] == "marketingqualifiedlead":
            return "Strong MQL"
        if f["lifecycle"] == "salesqualifiedlead":
            return "SQL ready for call"
        if f["visits"] > 15:
            return "High engagement"

        return "General follow-up recommended"

    # -----------------------------------------------------
    # Summary + reasoning
    # -----------------------------------------------------
    def generate_summary(self, props: Mapping[str, Any]) -> str:
        f = self._extract_features(props)
        firstname = f["props"].get("firstname") or "This contact"
        company = f["props"].get("company") or "Unknown company"

        return f"{firstname} from {company} has {f['visits']} recent visits."

    def generate_reasoning(self, props: Mapping[str, Any]) -> str:
        f = self._extract_features(props)
        reasons: list[str] = []

        if f["visits"] > 10:
            reasons.append("High engagement based on recent visits")
        elif f["visits"] > 5:
            reasons.append("Moderate engagement")
        else:
            reasons.append("Low engagement")

        if f["lifecycle"] in {"marketingqualifiedlead", "salesqualifiedlead"}:
            reasons.append("Qualified lifecycle stage")

        if f["has_company"]:
            reasons.append("Associated with a company")

        if f["has_email"]:
            reasons.append("Valid email present")

        return ". ".join(reasons) + "."

    # -----------------------------------------------------
    # Full contact analysis
    # -----------------------------------------------------
    def analyze_contact(self, contact: Mapping[str, Any]) -> AIContactAnalysis:
        props = self.normalize_contact_props(dict(contact.get("properties", {})))
        score = self.generate_score(props)

        return AIContactAnalysis(
            insight=self.generate_contact_insight(contact),
            score=score,
            score_reason=self.generate_score_reason(props, score),
            next_best_action=self.next_best_action(props),
            next_action=self.generate_next_action(props),
            next_action_reason=self.generate_next_action_reason(props),
            summary=self.generate_summary(props),
            reasoning=self.generate_reasoning(props),
        )

    def analyze_deal(self, deal: Mapping[str, Any]) -> AIContactAnalysis:
        return self.analyze_contact(deal)

    def analyze_company(self, company: Mapping[str, Any]) -> AIContactAnalysis:
        return self.analyze_contact(company)

    def analyze_lead(self, lead: Mapping[str, Any]) -> AIContactAnalysis:
        return self.analyze_contact(lead)

    # -----------------------------------------------------
    # Multi-object summarization
    # -----------------------------------------------------
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

        parts: list[str] = []
        if contacts:
            parts.append(f"{contacts} contact(s)")
        if leads:
            parts.append(f"{leads} lead(s)")
        if deals:
            parts.append(f"{deals} deal(s)")

        summary = " • ".join(parts)
        return f"🔎 *Summary:* Found {summary} matching your search."

    # -----------------------------------------------------
    # Top recommended actions
    # -----------------------------------------------------
    def top_recommended_actions(
        self,
        objects: Sequence[Mapping[str, Any]],
    ) -> list[str]:
        actions: list[tuple[int, str]] = []

        for obj in objects:
            props = self.normalize_contact_props(dict(obj.get("properties", {})))
            nba = self.next_best_action(props)
            score = self.generate_score(props)
            actions.append((score, nba))

        actions.sort(key=lambda x: x[0], reverse=True)

        seen: set[str] = set()
        top: list[str] = []

        for _, action in actions:
            if action not in seen:
                top.append(action)
                seen.add(action)
            if len(top) == 3:
                break

        return top

    # -----------------------------------------------------
    # Intent detection
    # -----------------------------------------------------
    def detect_intent(self, query: str) -> str:
        q = query.lower()

        if any(k in q for k in ["deal", "renewal", "contract", "pipeline", "amount"]):
            return "deal"

        if any(k in q for k in ["lead", "mql", "sql", "prospect"]):
            return "lead"

        return "contact"


# ---------------------------------------------------------
# Deal AI Service
# ---------------------------------------------------------
class AIDealService:
    def analyze_deal(self, deal: Mapping[str, Any]) -> AIDealAnalysis:
        props = deal.get("properties", {})
        name = props.get("dealname") or "This deal"
        amount = props.get("amount")
        stage = props.get("dealstage") or "Unknown stage"

        summary = f"{name} in stage '{stage}'"
        if amount:
            summary += f" with value {amount}"

        if stage.startswith("closedlost"):
            risk = "Lost"
            next_action = "Review loss reasons and update notes."
        elif stage.startswith("closedwon"):
            risk = "Won"
            next_action = "Ensure handoff to delivery / CS."
        else:
            risk = "Open"
            next_action = "Schedule next touchpoint with decision maker."

        return AIDealAnalysis(summary=summary, risk=risk, next_action=next_action)


# ---------------------------------------------------------
# Company AI Service
# ---------------------------------------------------------
class AICompanyService:
    def analyze_company(self, company: Mapping[str, Any]) -> AICompanyAnalysis:
        props = company.get("properties", {})
        name = props.get("name") or "This company"
        num_contacts = int(props.get("hs_num_contacts", 0) or 0)
        num_deals = int(props.get("num_associated_deals", 0) or 0)

        summary = f"{name} with {num_contacts} contacts and {num_deals} deals."

        if num_deals == 0:
            health = "Dormant"
            next_action = "Identify opportunities and create first deal."
        elif num_deals > 5:
            health = "Strategic"
            next_action = "Review account plan and upsell opportunities."
        else:
            health = "Active"
            next_action = "Schedule an account review."

        return AICompanyAnalysis(summary=summary, health=health, next_action=next_action)