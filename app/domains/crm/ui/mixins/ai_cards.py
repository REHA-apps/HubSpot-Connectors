from __future__ import annotations

from typing import Any

from app.core.models.ui import UnifiedCard
from app.domains.ai.service import (
    AICompanyAnalysis,
    AIContactAnalysis,
    AIDealAnalysis,
)

from .components import ComponentsMixin

MAX_LIST_DISPLAY = 25
MAX_OWNERS_DISPLAY = 100


class AICardsMixin(ComponentsMixin):
    def build_ai_insights(self, analysis: Any) -> UnifiedCard:
        subtitle = "Insights"
        emoji = "🤖"

        type_name = type(analysis).__name__
        if "Contact" in type_name:
            subtitle = "Contact Insights"
            emoji = "👤"
        elif "Deal" in type_name:
            subtitle = "Deal Insights"
            emoji = "💰"
        elif "Company" in type_name:
            subtitle = "Company Insights"
            emoji = "🏢"
        elif "Ticket" in type_name:
            subtitle = "Ticket Insights"
            emoji = "🎫"
        elif "Engagement" in type_name:
            subtitle = "Engagement Insights"
            emoji = "📞"

        summary = getattr(analysis, "insight", "") or getattr(analysis, "summary", "")
        next_action = getattr(analysis, "next_action", "") or getattr(
            analysis, "next_best_action", ""
        )
        reasoning = getattr(analysis, "reasoning", "") or getattr(
            analysis, "next_action_reason", ""
        )

        secondary = []
        if next_action:
            secondary.append(("Next Action", next_action))
        if reasoning:
            secondary.append(("Reasoning", reasoning))

        return UnifiedCard(
            title="AI Insights",
            subtitle=subtitle,
            emoji=emoji,
            content=summary,
            secondary_content=secondary,
        )

    def build_ai_scoring(self, analysis: Any) -> UnifiedCard:
        score = getattr(analysis, "score", "N/A")
        reason = getattr(analysis, "score_reason", "No scoring data available.")

        return UnifiedCard(
            title="AI Score",
            subtitle="Scoring Analysis",
            emoji="📊",
            metrics=[
                ("Score", str(score)),
            ],
            content=reason,
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
        secondary = [
            ("Health", analysis.health),
            ("Next Action", analysis.next_action),
        ]

        if analysis.top_actions:
            actions_text = "\n".join(f"• {action}" for action in analysis.top_actions)
            secondary.append(("Top Next Best Actions for Contacts", actions_text))

        return UnifiedCard(
            title="Company Insights",
            emoji="🏢",
            content=analysis.summary,
            secondary_content=secondary,
        )

    def build_deal_ai(self, analysis: AIDealAnalysis) -> UnifiedCard:
        """Builds a UnifiedCard for Deal-specific AI insights.

        Args:
            analysis (AIDealAnalysis): The deal AI analysis data.

        Returns:
            UnifiedCard: The rendered IR.

        """
        secondary = [
            ("Risk", analysis.risk),
            ("Next Action", analysis.next_action),
        ]

        if analysis.top_actions:
            actions_text = "\n".join(f"• {action}" for action in analysis.top_actions)
            secondary.append(("Top Next Best Actions for Contacts", actions_text))

        return UnifiedCard(
            title="Deal Insights",
            emoji="💰",
            content=analysis.summary,
            secondary_content=secondary,
        )
