# app/integrations/ai_service.py
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class AIService:
    """Lightweight AI heuristics for insights, scoring, and next-best-action."""

    @staticmethod
    def generate_contact_insight(contact: Mapping[str, Any]) -> str:
        props = contact.get("properties", {})
        firstname = props.get("firstname", "This contact")
        company = props.get("company", "Unknown Company")
        visits = props.get("hs_analytics_num_visits", 0)

        insight = f"💡 {firstname} works at {company}."

        if isinstance(visits, int) and visits > 5:
            insight += f" They are highly engaged with {visits} visits."
        else:
            insight += " Engagement is low."

        return insight

    @staticmethod
    def generate_score(props: Mapping[str, Any]) -> int:
        score = 0

        if props.get("hs_analytics_num_visits", 0) > 10:
            score += 40
        if props.get("lifecyclestage") in (
            "marketingqualifiedlead",
            "salesqualifiedlead",
        ):
            score += 30
        if props.get("company"):
            score += 10
        if props.get("email"):
            score += 10

        return min(score, 100)

    @staticmethod
    def next_best_action(props: Mapping[str, Any]) -> str:
        visits = props.get("hs_analytics_num_visits", 0)
        lifecycle = props.get("lifecyclestage")

        if lifecycle == "lead" and visits > 5:
            return "📞 Reach out — this lead is warming up."
        if lifecycle == "marketingqualifiedlead":
            return "🤝 Hand off to sales — strong MQL."
        if lifecycle == "salesqualifiedlead":
            return "📅 Schedule a discovery call."
        if visits > 15:
            return "🔥 High engagement — follow up immediately."

        return "📝 Add a note or send a follow-up email."

    @staticmethod
    def summarize_results(objects: Sequence[Mapping[str, Any]]) -> str:
        """Produces a short AI-style summary of all results."""
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

    @staticmethod
    def top_recommended_actions(objects: Sequence[Mapping[str, Any]]) -> list[str]:
        """Returns the top 3 recommended actions across all objects."""
        actions = []

        for obj in objects:
            props = obj.get("properties", {})
            nba = AIService.next_best_action(props)
            score = AIService.generate_score(props)
            actions.append((score, nba))

        # Sort by score descending
        actions.sort(key=lambda x: x[0], reverse=True)

        # Return top 3 unique actions
        seen = set()
        top = []
        for _, action in actions:
            if action not in seen:
                top.append(action)
                seen.add(action)
            if len(top) == 3:
                break

        return top

    @staticmethod
    def detect_intent(query: str) -> str:
        """Lightweight intent detection for /hs command.
        Returns: "contact", "lead", "deal"
        """
        q = query.lower()

        # Deal-like keywords
        if any(k in q for k in ["deal", "renewal", "contract", "pipeline", "amount"]):
            return "deal"

        # Lead-like keywords
        if any(k in q for k in ["lead", "mql", "sql", "prospect"]):
            return "lead"

        # Default → contact
        return "contact"

    @staticmethod
    def enrich_contact(contact: Mapping[str, Any]) -> dict[str, Any]:
        props = contact.get("properties", {})
        return {
            "insight": AIService.generate_contact_insight(contact),
            "score": AIService.generate_score(props),
            "next_best_action": AIService.next_best_action(props),
        }

    # ai = AIService.enrich_contact(contact)
