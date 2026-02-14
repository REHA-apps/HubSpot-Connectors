from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.integrations.ai_service import AIContactAnalysis

SlackMessage = dict[str, Any]
SlackBlock = dict[str, Any]


# ------------------------------------------------------------
# MAPPINGS
# ------------------------------------------------------------

DEAL_STAGE_EMOJI = {
    "appointmentscheduled": "📅",
    "qualifiedtobuy": "🔍",
    "presentationscheduled": "🎤",
    "decisionmakerboughtin": "🤝",
    "contractsent": "📄",
    "closedwon": "🏆",
    "closedlost": "❌",
}

LIFECYCLE_BADGES = {
    "subscriber": "🟦 Subscriber",
    "lead": "🟩 Lead",
    "marketingqualifiedlead": "🟧 MQL",
    "salesqualifiedlead": "🟥 SQL",
    "opportunity": "🟪 Opportunity",
    "customer": "🟨 Customer",
    "evangelist": "⭐ Evangelist",
}


# ------------------------------------------------------------
# SCORE BAR
# ------------------------------------------------------------


def score_bar(score: int) -> str:
    filled = int(score / 10)
    empty = 10 - filled
    return f"{'🟩' * filled}{'⬜' * empty}  `{score}`"


# ------------------------------------------------------------
# SHARED BLOCK HELPERS
# ------------------------------------------------------------


def header_block(text: str) -> SlackBlock:
    return {"type": "header", "text": {"type": "plain_text", "text": text}}


def markdown_block(text: str) -> SlackBlock:
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


# ------------------------------------------------------------
# CONTACT CARD
# ------------------------------------------------------------


def build_contact_card(
    contact: Mapping[str, Any],
    analysis: AIContactAnalysis,
) -> SlackMessage:
    props = contact.get("properties", {}) or {}

    firstname = props.get("firstname", "")
    lastname = props.get("lastname", "")
    email = props.get("email", "unknown@example.com")
    name = f"{firstname} {lastname}".strip() or email

    lifecycle = props.get("lifecyclestage", "subscriber")
    lifecycle_badge = LIFECYCLE_BADGES.get(lifecycle, lifecycle)

    visits = props.get("hs_analytics_num_visits", 0)

    blocks = [
        header_block(name),
        markdown_block(
            f"*Email:* <{email}>\n"
            f"*Lifecycle:* {lifecycle_badge}\n"
            f"*Engagement:* {visits} visits\n"
            f"*Score:* {score_bar(analysis.score)}"
        ),
        markdown_block(analysis.insight),
        markdown_block(f"*Next Best Action:* {analysis.next_best_action}"),
    ]

    return {"blocks": blocks}


# ------------------------------------------------------------
# LEAD CARD
# ------------------------------------------------------------


def build_lead_card(
    lead: Mapping[str, Any],
    analysis: AIContactAnalysis,
) -> SlackMessage:
    props = lead.get("properties", {})
    firstname = props.get("firstname", "")
    lastname = props.get("lastname", "")
    email = props.get("email", "unknown@example.com")
    name = f"{firstname} {lastname}".strip() or email

    blocks = [
        header_block(f"Lead: {name}"),
        markdown_block(f"*Email:* <{email}>\n*Score:* {score_bar(analysis.score)}"),
        markdown_block(analysis.insight),
        markdown_block(f"*Next Best Action:* {analysis.next_best_action}"),
    ]

    return {"blocks": blocks}


# ------------------------------------------------------------
# DEAL CARD
# ------------------------------------------------------------


def build_deal_card(
    deal: Mapping[str, Any],
    analysis: AIContactAnalysis,
) -> SlackMessage:
    props = deal.get("properties", {})
    name = props.get("dealname", "Unnamed Deal")
    amount = props.get("amount", "N/A")
    stage = props.get("dealstage", "Unknown")
    stage_emoji = DEAL_STAGE_EMOJI.get(stage, "💼")

    blocks = [
        header_block(f"Deal: {name}"),
        markdown_block(
            f"*Amount:* ${amount}\n"
            f"*Stage:* {stage_emoji} `{stage}`\n"
            f"*Score:* {score_bar(analysis.score)}"
        ),
        markdown_block(analysis.insight),
        markdown_block(f"*Next Best Action:* {analysis.next_best_action}"),
    ]

    return {"blocks": blocks}


# ------------------------------------------------------------
# UNIFIED CARD BUILDER
# ------------------------------------------------------------


def build_card(
    obj: Mapping[str, Any],
    analysis: AIContactAnalysis,
) -> SlackMessage:
    props = obj.get("properties", {})

    if "dealname" in props:
        return build_deal_card(obj, analysis)

    if props.get("lifecyclestage") == "lead":
        return build_lead_card(obj, analysis)

    return build_contact_card(obj, analysis)
