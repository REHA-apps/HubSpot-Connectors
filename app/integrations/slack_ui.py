# app/integrations/slack_ui.py
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.integrations.ai_service import AIService

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
# CONTACT CARD
# ------------------------------------------------------------


def build_contact_card(contact: Mapping[str, Any], ai_summary: str) -> SlackMessage:
    props = contact.get("properties", {}) or {}

    firstname = props.get("firstname", "")
    lastname = props.get("lastname", "")
    email = props.get("email", "unknown@example.com")
    name = f"{firstname} {lastname}".strip() or email

    lifecycle = props.get("lifecyclestage", "subscriber")
    lifecycle_badge = LIFECYCLE_BADGES.get(lifecycle, lifecycle)

    visits = props.get("hs_analytics_num_visits", 0)
    score = AIService.generate_score(props)
    nba = AIService.next_best_action(props)

    blocks: list[SlackBlock] = [
        {"type": "header", "text": {"type": "plain_text", "text": name}},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Email:* <{email}>\n"
                    f"*Lifecycle:* {lifecycle_badge}\n"
                    f"*Engagement:* {visits} visits\n"
                    f"*Score:* {score_bar(score)}"
                ),
            },
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": ai_summary}},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Next Best Action:* {nba}"},
        },
    ]

    return {"blocks": blocks}


# ------------------------------------------------------------
# LEAD CARD
# ------------------------------------------------------------


def build_lead_card(lead: Mapping[str, Any], ai_summary: str) -> SlackMessage:
    props = lead.get("properties", {})
    firstname = props.get("firstname", "")
    lastname = props.get("lastname", "")
    email = props.get("email", "unknown@example.com")
    name = f"{firstname} {lastname}".strip() or email

    score = AIService.generate_score(props)
    nba = AIService.next_best_action(props)

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"Lead: {name}"}},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Email:* <{email}>\n*Score:* {score_bar(score)}",
            },
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": ai_summary}},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Next Best Action:* {nba}"},
        },
    ]

    return {"blocks": blocks}


# ------------------------------------------------------------
# DEAL CARD
# ------------------------------------------------------------


def build_deal_card(deal: Mapping[str, Any], ai_summary: str) -> SlackMessage:
    props = deal.get("properties", {})
    name = props.get("dealname", "Unnamed Deal")
    amount = props.get("amount", "N/A")
    stage = props.get("dealstage", "Unknown")
    stage_emoji = DEAL_STAGE_EMOJI.get(stage, "💼")

    score = AIService.generate_score(props)
    nba = AIService.next_best_action(props)

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"Deal: {name}"}},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Amount:* ${amount}\n"
                    f"*Stage:* {stage_emoji} `{stage}`\n"
                    f"*Score:* {score_bar(score)}"
                ),
            },
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": ai_summary}},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Next Best Action:* {nba}"},
        },
    ]

    return {"blocks": blocks}


# ------------------------------------------------------------
# UNIFIED CARD BUILDER
# ------------------------------------------------------------


def build_card(obj: Mapping[str, Any], ai_summary: str) -> SlackMessage:
    props = obj.get("properties", {})

    if "dealname" in props:
        return build_deal_card(obj, ai_summary)

    if props.get("lifecyclestage") == "lead":
        return build_lead_card(obj, ai_summary)

    return build_contact_card(obj, ai_summary)


def build_contact_payload(contact: Mapping[str, Any]) -> SlackMessage:
    ai_summary = AIService.generate_contact_insight(contact)
    return build_contact_card(contact, ai_summary)
