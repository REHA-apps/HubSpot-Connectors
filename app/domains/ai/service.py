from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.core.logging import get_logger
from app.db.storage_service import StorageService
from app.utils.parsers import to_int

logger = get_logger("ai.service")

# ==========================================================
# CONFIG
# ==========================================================

QUALIFIED_STAGES = {"marketingqualifiedlead", "salesqualifiedlead"}


@dataclass(frozen=True)
class ScoringConfig:
    visit_threshold_moderate: int = 5
    visit_threshold_high: int = 10
    visit_threshold_very_high: int = 15

    weight_high_visit: int = 30
    weight_moderate_visit: int = 15
    weight_qualified_lifecycle: int = 25
    weight_has_company: int = 10
    weight_has_email: int = 10

    weight_recency_bonus_high: int = 15
    weight_recency_bonus_medium: int = 8
    weight_recency_bonus_low: int = 3

    weight_velocity_bonus: int = 15
    weight_stage_stale_penalty: int = -15

    max_score: int = 100

    engagement_recent_bonus: int = 10
    engagement_high_activity_bonus: int = 15
    engagement_stale_penalty: int = -10
    deal_recent_activity_risk_reduction: int = -15


# ==========================================================
# DATA MODELS
# ==========================================================


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
    top_actions: list[str] | None = None


@dataclass(frozen=True)
class AIDealAnalysis:
    summary: str
    risk: str
    next_action: str
    score: int
    score_reason: str
    top_actions: list[str] | None = None


@dataclass(frozen=True)
class AITicketAnalysis:
    summary: str
    urgency: str
    next_action: str


@dataclass(frozen=True)
class AITaskAnalysis:
    summary: str
    status_label: str
    next_action: str


@dataclass(frozen=True)
class AIConversationAnalysis:
    summary: str
    status: str
    next_action: str


@dataclass(frozen=True)
class AIEngagementAnalysis:
    summary: str
    engagement_type: str
    next_action: str


@dataclass(frozen=True)
class AIThreadSummary:
    summary: str
    key_points: list[str]
    sentiment: str


@dataclass(frozen=True)
class AILeadAnalysis:
    summary: str
    status_label: str
    next_action: str
    score: int


@dataclass(frozen=True)
class AICommunicationAnalysis:
    summary: str
    channel: str
    next_action: str


@dataclass(frozen=True)
class AIAppointmentAnalysis:
    summary: str
    status_label: str
    next_action: str


# ==========================================================
# SERVICE (STATELESS + MULTI-TENANT SAFE)
# ==========================================================


class AIService:
    def __init__(self, corr_id: str) -> None:
        self.storage = StorageService(corr_id)

    # ------------------------------------------------------
    # CONFIG (NEVER STORED ON SELF)
    # ------------------------------------------------------

    async def _get_workspace_config(self, workspace_id: str | None) -> ScoringConfig:
        if not workspace_id:
            return ScoringConfig()

        record = await self.storage.ensure_scoring_config(workspace_id)

        return ScoringConfig(
            visit_threshold_moderate=record.visit_threshold_moderate,
            visit_threshold_high=record.visit_threshold_high,
            visit_threshold_very_high=record.visit_threshold_very_high,
            weight_high_visit=record.weight_high_visit,
            weight_moderate_visit=record.weight_moderate_visit,
            weight_qualified_lifecycle=record.weight_qualified_lifecycle,
            weight_has_company=record.weight_has_company,
            weight_has_email=record.weight_has_email,
            weight_recency_bonus_high=record.weight_recency_bonus_high,
            weight_recency_bonus_medium=record.weight_recency_bonus_medium,
            weight_recency_bonus_low=record.weight_recency_bonus_low,
            weight_velocity_bonus=record.weight_velocity_bonus,
            weight_stage_stale_penalty=record.weight_stage_stale_penalty,
            max_score=record.max_score,
        )

    # ------------------------------------------------------
    # FEATURE EXTRACTION
    # ------------------------------------------------------

    def _extract_features(self, props: Mapping[str, Any]) -> dict[str, Any]:
        props = dict(props)
        props["hs_analytics_num_visits"] = (
            to_int(props.get("hs_analytics_num_visits")) or 0
        )

        return {
            "props": props,
            "visits": props["hs_analytics_num_visits"],
            "lifecycle": (props.get("lifecyclestage") or "").lower(),
            "has_company": bool(props.get("company")),
            "has_email": bool(props.get("email")),
        }

    # ------------------------------------------------------
    # SCORING ENGINE
    # ------------------------------------------------------

    def _recency_bonus(self, props: Mapping[str, Any], cfg: ScoringConfig) -> int:
        last = props.get("lastmodifieddate")
        if not last:
            return 0
        try:
            dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
            days = (datetime.now(UTC) - dt).days
            if days <= 2:  # noqa: PLR2004
                return cfg.weight_recency_bonus_high
            if days <= 7:  # noqa: PLR2004
                return cfg.weight_recency_bonus_medium
            if days <= 30:  # noqa: PLR2004
                return cfg.weight_recency_bonus_low
        except Exception:
            return 0
        return 0

    def _velocity_bonus(self, props: Mapping[str, Any], cfg: ScoringConfig) -> int:
        recent = to_int(props.get("recent_visits_7d")) or 0
        lifetime = to_int(props.get("hs_analytics_num_visits")) or 0
        if lifetime == 0:
            return 0
        if recent >= 3 and (recent / lifetime) >= 0.5:  # noqa: PLR2004
            return cfg.weight_velocity_bonus
        return 0

    def generate_score(
        self,
        props: Mapping[str, Any],
        cfg: ScoringConfig,
    ) -> int:
        f = self._extract_features(props)
        score = 0

        if f["visits"] >= cfg.visit_threshold_very_high:
            score += cfg.weight_high_visit
        elif f["visits"] >= cfg.visit_threshold_high:
            score += int(cfg.weight_high_visit * 0.8)
        elif f["visits"] >= cfg.visit_threshold_moderate:
            score += cfg.weight_moderate_visit

        if f["lifecycle"] in QUALIFIED_STAGES:
            score += cfg.weight_qualified_lifecycle

        if f["has_company"]:
            score += cfg.weight_has_company

        if f["has_email"]:
            score += cfg.weight_has_email

        score += self._recency_bonus(f["props"], cfg)
        score += self._velocity_bonus(f["props"], cfg)

        return max(0, min(score, cfg.max_score))

    def _stage_staleness_penalty(
        self,
        props: Mapping[str, Any],
        cfg: ScoringConfig,
    ) -> int:
        entered = props.get("hs_date_entered_stage")
        if not entered:
            return 0
        try:
            dt = datetime.fromisoformat(entered.replace("Z", "+00:00"))
            if (datetime.now(UTC) - dt).days > 30:  # noqa: PLR2004
                return cfg.weight_stage_stale_penalty
        except Exception:
            return 0
        return 0

    def _extract_engagement_datetime(
        self,
        engagement: Mapping[str, Any],
    ) -> datetime | None:
        """Safely extract a datetime from any HubSpot engagement shape.
        Supports:
        - CRM v3 (properties.hs_timestamp)
        - Meetings (hs_meeting_start_time)
        - createdate / hs_createdate
        - Legacy engagements API (engagement.timestamp)
        - Milliseconds and seconds
        """
        ts = None

        # CRM v3 structure
        props = engagement.get("properties") or {}
        ts = (
            props.get("hs_timestamp")
            or props.get("hs_meeting_start_time")
            or props.get("createdate")
            or props.get("hs_createdate")
        )

        # Legacy engagement API
        if not ts and "engagement" in engagement:
            ts = engagement.get("engagement", {}).get("timestamp")

        if not ts:
            return None

        try:
            # Milliseconds or seconds
            if isinstance(ts, int | float):
                # Heuristic: ms are 13 digits
                if ts > 10_000_000_000:  # noqa: PLR2004
                    return datetime.fromtimestamp(ts / 1000, tz=UTC)
                return datetime.fromtimestamp(ts, tz=UTC)

            # ISO string
            return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))

        except Exception:
            return None

    def _engagement_metrics(
        self,
        engagements: Sequence[Mapping[str, Any]] | None,
    ) -> dict[str, Any]:
        if not engagements:
            return {
                "count_30d": 0,
                "recent": False,
                "last_activity_days": None,
            }

        now = datetime.now(UTC)
        count_30d = 0
        last_days = None

        for e in engagements:
            dt = self._extract_engagement_datetime(e)

            if not dt:
                continue
            days = (now - dt).days

            if last_days is None or days < last_days:
                last_days = days

            if days <= 30:  # noqa: PLR2004
                count_30d += 1

        return {
            "count_30d": count_30d,
            "recent": last_days is not None and last_days <= 7,  # noqa: PLR2004
            "last_activity_days": last_days,
        }

    def _format_engagements(
        self, engagements: Sequence[Mapping[str, Any]] | None
    ) -> str:
        if not engagements:
            return ""

        lines = ["\n**Recent Engagements:**"]

        sorted_engs = []
        for e in engagements:
            dt = self._extract_engagement_datetime(e)
            if dt:
                sorted_engs.append((dt, e))

        sorted_engs.sort(key=lambda x: x[0], reverse=True)

        for dt, e in sorted_engs[:5]:
            etype = e.get("_engagement_type", "")
            props = e.get("properties") or {}

            dt_str = dt.strftime("%B %d, %Y, at %I:%M %p")

            if etype == "meetings":
                title = props.get("hs_meeting_title", "Meeting")
                lines.append(
                    f"• 📅 **Meeting**: Scheduled for {dt_str} about '{title}'"
                )
            elif etype == "emails":
                subject = props.get("hs_email_subject", "Email")
                lines.append(
                    f"• ✉️ **Email**: Logged on {dt_str} with subject '{subject}'"
                )
            elif etype == "calls":
                title = props.get("hs_call_title", "Call")
                lines.append(
                    f"• 📞**Call**: Took place on {dt_str} regarding '{title}'"
                )
            elif etype == "tasks":
                subject = props.get("hs_task_subject", "Task")
                lines.append(f"• ✅ **Task**: Created on {dt_str} to '{subject}'")
            elif etype == "notes":
                body = props.get("hs_note_body", "")
                # Clean up HTML since no _strip_html is natively here
                import re

                body = re.sub(r"<[^>]+>", " ", body).strip()
                if len(body) > 60:
                    body = body[:57] + "..."
                if body:
                    lines.append(f"• 📝 **Note**: Logged on {dt_str} — '{body}'")
                else:
                    lines.append(f"• 📝 **Note**: Logged on {dt_str}")
            else:
                lines.append(f"• 📌 **Activity**: Logged on {dt_str}")

        return "\n".join(lines)

    def _format_associated_objects(
        self, associated_objects: dict[str, list[dict[str, Any]]] | None
    ) -> str:
        """Format associated CRM objects as text for Slack messages."""
        if not associated_objects:
            return ""

        lines = ["\n**Associations:**"]
        # Contacts
        contacts = (associated_objects or {}).get("contacts", [])
        if contacts:
            for c in contacts[:5]:
                props = c.get("properties") or {}
                name = (
                    f"{props.get('firstname', '')} {props.get('lastname', '')}".strip()
                    or props.get("email", "Contact")
                )
                lines.append(f"• 👤 {name}")

        # Companies
        companies = (associated_objects or {}).get("companies", [])
        if companies:
            for c in companies[:5]:
                props = c.get("properties") or {}
                name = props.get("name", "Company")
                lines.append(f"• 🏢 {name}")

        # Deals
        deals = (associated_objects or {}).get("deals", [])
        if deals:
            for d in deals[:5]:
                props = d.get("properties") or {}
                name = props.get("dealname", "Deal")
                amount = props.get("amount") or ""
                lines.append(f"• 💰 {name} ({amount})")

        # Tickets
        tickets = (associated_objects or {}).get("tickets", [])
        if tickets:
            for t in tickets[:5]:
                props = t.get("properties") or {}
                subject = props.get("subject", "Unknown Ticket")
                priority = props.get("hs_ticket_priority", "Normal")
                lines.append(f"• 🎟️ {subject} (Priority: {priority})")

        return "\n".join(lines)

    # ======================================================
    # POLYMORPHIC ENTRY
    # ======================================================

    async def analyze_polymorphic(
        self,
        obj: Mapping[str, Any],
        object_type: str,
        **kwargs: Any,
    ) -> (
        AIContactAnalysis
        | AICompanyAnalysis
        | AIDealAnalysis
        | AITicketAnalysis
        | AITaskAnalysis
        | AILeadAnalysis
        | AICommunicationAnalysis
        | AIAppointmentAnalysis
        | AIConversationAnalysis
        | AIEngagementAnalysis
    ):
        """Dispatches to the correct analyzer based on HubSpot object type or ID."""
        # Handle both string types ("contact") and numeric IDs ("0-1")
        object_type = str(object_type).lower()

        # Engagement collection - respect overrides in kwargs
        engagements = kwargs.pop("engagements", obj.get("engagements") or [])
        associated_objects = kwargs.pop(
            "associated_objects", obj.get("associated_objects") or {}
        )

        match object_type:
            case "contact" | "0-1":
                return await self.analyze_contact(
                    obj,
                    engagements=engagements,
                    associated_objects=associated_objects,
                    **kwargs,
                )
            case "company" | "0-2":
                return await self.analyze_company(
                    obj,
                    engagements=engagements,
                    associated_objects=associated_objects,
                    **kwargs,
                )
            case "deal" | "0-3":
                return await self.analyze_deal(
                    obj,
                    engagements=engagements,
                    associated_objects=associated_objects,
                    **kwargs,
                )
            case "ticket" | "0-5":
                return await self.analyze_ticket(
                    obj,
                    associated_objects=associated_objects,
                    **kwargs,
                )
            case "task" | "0-27":
                return await self.analyze_task(obj, **kwargs)
            case "lead" | "0-13" | "0-136":
                return await self.analyze_lead(obj, **kwargs)
            case "communication" | "0-18":
                return await self.analyze_communication(obj, **kwargs)
            case "appointment" | "0-421":
                return await self.analyze_appointment(obj, **kwargs)
            case "conversation":
                return await self.analyze_conversation(obj, **kwargs)
            case (
                "call"
                | "meeting"
                | "email"
                | "note"
                | "0-48"
                | "0-47"
                | "0-49"
                | "0-46"
                | "0-9"
            ):
                return await self.analyze_engagement(obj, **kwargs)
            case _:
                raise ValueError(f"Unsupported object type: {object_type}")

    # ======================================================
    # CONTACT
    # ======================================================

    async def analyze_contact(
        self,
        obj: Mapping[str, Any],
        engagements: Sequence[Mapping[str, Any]] | None = None,
        associated_objects: dict[str, list[dict[str, Any]]] | None = None,
        include_associations: bool = True,
        **kwargs: Any,
    ) -> AIContactAnalysis:
        props = obj.get("properties") or {}
        workspace_id = obj.get("workspace_id")

        cfg = await self._get_workspace_config(workspace_id)

        score = self.generate_score(props, cfg)

        metrics = self._engagement_metrics(engagements)

        # Engagement influence
        if metrics["recent"]:
            score += cfg.engagement_recent_bonus

        if metrics["count_30d"] >= 5:  # noqa: PLR2004
            score += cfg.engagement_high_activity_bonus

        last_act = metrics["last_activity_days"]
        if last_act is not None and last_act > 30:  # noqa: PLR2004
            score += cfg.engagement_stale_penalty

        score = max(0, min(score, cfg.max_score))

        summary = self._contact_summary(props, metrics)

        engagements_text = self._format_engagements(engagements)
        assoc_text = ""
        if include_associations:
            assoc_text = self._format_associated_objects(associated_objects)

        insight = summary + engagements_text + assoc_text

        return AIContactAnalysis(
            insight=insight,
            score=score,
            score_reason=self._contact_reasoning(props, cfg, score),
            next_best_action=self._next_action(props, metrics),
            next_action=self._next_action(props, metrics),
            next_action_reason="Adjusted for engagement behavior.",
            summary=summary,
            reasoning=self._contact_reasoning(props, cfg, score),
        )

    def _contact_summary(
        self,
        props: Mapping[str, Any],
        metrics: dict[str, Any] | None = None,
    ) -> str:
        name = (
            f"{props.get('firstname', '')} {props.get('lastname', '')}".strip()
            or "Contact"
        )
        company = props.get("company", "Unknown company")
        visits = to_int(props.get("hs_analytics_num_visits")) or 0
        lifecycle = (props.get("lifecyclestage") or "").lower()

        # Readable lifecycle label
        stage_labels = {
            "subscriber": "Subscriber",
            "lead": "Lead",
            "marketingqualifiedlead": "MQL",
            "salesqualifiedlead": "SQL",
            "opportunity": "Opportunity",
            "customer": "Customer",
            "evangelist": "Evangelist",
            "other": "Other",
        }
        stage_label = stage_labels.get(lifecycle, lifecycle.title() or "Unknown")

        parts = [f"{name} ({stage_label}) at {company}"]
        parts.append(f"{visits} visits")

        if metrics:
            count_30d = metrics.get("count_30d", 0)
            last_days = metrics.get("last_activity_days")
            if count_30d:
                parts.append(f"{count_30d} engagements in 30d")
            if last_days is not None:
                if last_days == 0:
                    parts.append("last active today")
                elif last_days == 1:
                    parts.append("last active yesterday")
                else:
                    parts.append(f"last active {last_days}d ago")

        return " — ".join(parts[:2]) + ", " + ", ".join(parts[2:]) + "."

    def _contact_reasoning(
        self,
        props: Mapping[str, Any],
        cfg: ScoringConfig,
        total_score: int = 0,
    ) -> str:
        f = self._extract_features(props)
        parts: list[str] = []

        # Visit contribution
        if f["visits"] >= cfg.visit_threshold_very_high:
            parts.append(f"+{cfg.weight_high_visit}pts visits ({f['visits']})")
        elif f["visits"] >= cfg.visit_threshold_high:
            pts = int(cfg.weight_high_visit * 0.8)
            parts.append(f"+{pts}pts visits ({f['visits']})")
        elif f["visits"] >= cfg.visit_threshold_moderate:
            parts.append(f"+{cfg.weight_moderate_visit}pts visits ({f['visits']})")

        if f["lifecycle"] in QUALIFIED_STAGES:
            parts.append(f"+{cfg.weight_qualified_lifecycle}pts qualified stage")

        if f["has_company"]:
            parts.append(f"+{cfg.weight_has_company}pts company")
        if f["has_email"]:
            parts.append(f"+{cfg.weight_has_email}pts email")

        recency = self._recency_bonus(f["props"], cfg)
        if recency:
            parts.append(f"+{recency}pts recency")

        velocity = self._velocity_bonus(f["props"], cfg)
        if velocity:
            parts.append(f"+{velocity}pts velocity")

        return (
            f"Score {total_score}: " + ", ".join(parts)
            if parts
            else f"Score {total_score}: baseline"
        )

    def _next_action(
        self,
        props: Mapping[str, Any],
        metrics: dict[str, Any] | None = None,
    ) -> str:
        f = self._extract_features(props)
        last_days = metrics.get("last_activity_days") if metrics else None
        count_30d = metrics.get("count_30d", 0) if metrics else 0

        # Stale contact — re-engage
        if last_days is not None and last_days > 14:  # noqa: PLR2004
            return (
                f"No activity in {last_days} days — re-engage with a value-add email."
            )

        # High recent activity — capitalize
        if count_30d >= 5:  # noqa: PLR2004
            return (
                f"{count_30d} engagements in 30 days "
                "— propose next steps before momentum fades."
            )

        # SQL ready for sales
        if f["lifecycle"] == "salesqualifiedlead":
            return "SQL status — schedule discovery call."

        # MQL needs nurturing
        if f["lifecycle"] == "marketingqualifiedlead":
            return "MQL status — nurture with targeted content."

        # New lead with high visits
        if f["lifecycle"] == "lead" and f["visits"] >= 5:  # noqa: PLR2004
            return f"Lead with {f['visits']} visits — schedule intro call within 48h."

        # High intent visitor
        if f["visits"] >= 15:  # noqa: PLR2004
            return f"High intent ({f['visits']} visits) — prioritize follow-up."

        # Recently active but low engagement
        if last_days is not None and last_days <= 2:  # noqa: PLR2004
            return "Recently active — send a timely follow-up."

        return "Add follow-up task."

    # ======================================================
    # COMPANY
    # ======================================================

    async def analyze_company(
        self,
        company: Mapping[str, Any],
        engagements: Sequence[Mapping[str, Any]] | None = None,
        associated_objects: dict[str, list[dict[str, Any]]] | None = None,
        include_associations: bool = True,
        **kwargs: Any,
    ) -> AICompanyAnalysis:
        props = company.get("properties") or {}
        name = props.get("name", "Company")
        visits = to_int(props.get("hs_analytics_num_visits")) or 0
        industry = props.get("industry") or ""
        employees = to_int(props.get("numberofemployees")) or 0

        # Count associated objects
        n_contacts = len((associated_objects or {}).get("contacts", []))
        n_deals = len((associated_objects or {}).get("deals", []))

        # Multi-factor health
        health_score = 0
        if visits > 10:  # noqa: PLR2004
            health_score += 1
        if n_contacts >= 2:  # noqa: PLR2004
            health_score += 1
        if n_deals >= 1:
            health_score += 1

        if health_score >= 3:  # noqa: PLR2004
            health = "Strong"
            next_action = "Expand footprint — identify new stakeholders."
        elif health_score >= 2:  # noqa: PLR2004
            health = "Healthy"
            next_action = "Maintain momentum — schedule quarterly review."
        elif health_score >= 1:
            health = "Needs Attention"
            next_action = "Re-engage — no recent activity or few contacts."
        else:
            health = "At Risk"
            next_action = "Investigate — no visits, contacts, or deals."

        top = None
        if associated_objects and "contacts" in associated_objects:
            top = await self.top_recommended_actions(
                associated_objects["contacts"],
                company.get("workspace_id"),
            )

        # Build rich summary
        parts = [name]
        if industry:
            parts[0] += f" ({industry})"
        if employees:
            parts.append(f"{employees} employees")
        parts.append(f"{visits} visits")
        parts.append(f"{n_contacts} contacts")
        parts.append(f"{n_deals} active deals")

        summary = ", ".join(parts) + "."
        if include_associations:
            summary += self._format_associated_objects(associated_objects)

        return AICompanyAnalysis(
            summary=summary,
            health=health,
            next_action=next_action,
            top_actions=top,
        )

    # ======================================================
    # DEAL
    # ======================================================

    async def analyze_deal(
        self,
        deal: Mapping[str, Any],
        engagements: Sequence[Mapping[str, Any]] | None = None,
        associated_objects: dict[str, list[dict[str, Any]]] | None = None,
        include_associations: bool = True,
        owner_name: str | None = None,
        **kwargs: Any,
    ) -> AIDealAnalysis:
        props = deal.get("properties") or {}
        workspace_id = deal.get("workspace_id")
        cfg = await self._get_workspace_config(workspace_id)

        # Basic engagement metrics
        metrics = self._engagement_metrics(engagements)
        last_act = metrics["last_activity_days"]

        # Risk Score (0-100)
        score = 50 + self._stage_staleness_penalty(props, cfg)
        if metrics["recent"]:
            score += cfg.deal_recent_activity_risk_reduction
        if last_act is not None and last_act > 30:  # noqa: PLR2004
            score += 10

        stage = (props.get("dealstage") or "").lower()
        deal_name = props.get("dealname", "Deal")
        amount = props.get("amount") or ""

        # Stage label
        stage_labels = {
            "appointmentscheduled": "Appointment Scheduled",
            "qualifiedtobuy": "Qualified to Buy",
            "presentationscheduled": "Presentation Scheduled",
            "decisionmakerboughtin": "Decision Maker Bought In",
            "contractsent": "Contract Sent",
            "closedwon": "Closed Won",
            "closedlost": "Closed Lost",
        }
        stage_label = stage_labels.get(stage, stage.replace("_", " ").title())

        # Closing status
        close_date = props.get("closedate")
        close_days = None
        if close_date:
            try:
                close_dt = datetime.fromisoformat(close_date.replace("Z", "+00:00"))
                close_days = (close_dt - datetime.now(UTC)).days
            except Exception:
                pass

        # Determine risk and next action
        if stage.startswith("closedlost"):
            risk = "Lost"
            next_action = "Review loss reasons and document learnings."
        elif stage.startswith("closedwon"):
            risk = "Won"
            next_action = "Handoff to onboarding."
        elif last_act is not None and last_act > 14:  # noqa: PLR2004
            risk = "Stalling"
            next_action = (
                f"No activity in {last_act} days — re-engage before deal goes cold."
            )
        elif close_days is not None and 0 < close_days <= 7:  # noqa: PLR2004
            risk = "Closing Soon"
            next_action = (
                f"Closing in {close_days} days — confirm commitment and finalize terms."
            )
        elif close_days is not None and close_days < 0:
            risk = "Overdue"
            next_action = "Close date passed — update timeline or close."
        else:
            risk = "Open"
            next_action = "Ensure next meeting is scheduled."

        # Rich summary: Deal Name ($Amount) — Owned by [Name]
        main_parts = [deal_name]
        if amount:
            main_parts[0] += f" (${amount})"
        if owner_name:
            main_parts.append(f"Owned by {owner_name}")

        extra_parts = []
        if close_days is not None and close_days > 0:
            extra_parts.append(f"closing in {close_days}d")
        elif close_days is not None and close_days < 0:
            extra_parts.append(f"overdue by {abs(close_days)}d")
        if last_act is not None:
            extra_parts.append(f"last activity {last_act}d ago")

        summary = " — ".join(main_parts)
        if extra_parts:
            summary += ", " + ", ".join(extra_parts)
        summary += "."

        if include_associations:
            summary += self._format_associated_objects(associated_objects)
        summary += self._format_engagements(engagements)

        return AIDealAnalysis(
            summary=summary,
            risk=risk,
            next_action=next_action,
            score=max(0, min(score, 100)),
            score_reason=f"Risk {score}/100: stage={stage_label}, "
            f"activity={'recent' if metrics['recent'] else 'stale'}.",
            top_actions=None,
        )

    # ======================================================
    # TICKET
    # ======================================================

    async def analyze_ticket(
        self,
        ticket: Mapping[str, Any],
        associated_objects: dict[str, list[dict[str, Any]]] | None = None,
        include_associations: bool = True,
        **kwargs: Any,
    ) -> AITicketAnalysis:
        props = ticket.get("properties") or {}
        subject = props.get("subject", "Ticket")
        priority = (props.get("hs_ticket_priority") or "").upper()
        category = props.get("hs_ticket_category") or ""
        created = props.get("createdate") or ""

        # Ticket age
        age_days = None
        if created:
            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                age_days = (datetime.now(UTC) - dt).days
            except Exception:
                pass

        # Urgency + action based on priority + age
        if priority == "HIGH":
            urgency = "Critical"
            if age_days is not None and age_days > 3:  # noqa: PLR2004
                next_action = f"HIGH priority open {age_days}d — escalate immediately."
            else:
                next_action = "Assign and respond within 4 hours."
        elif priority == "MEDIUM":
            urgency = "Moderate"
            if age_days is not None and age_days > 7:  # noqa: PLR2004
                next_action = f"Open {age_days} days — follow up or escalate."
            else:
                next_action = "Triage and assign within 24 hours."
        else:
            urgency = "Low"
            next_action = "Review in next cycle."

        # Rich summary
        parts = [subject, f"Priority: {priority or 'Normal'}"]
        if category:
            parts.append(f"Category: {category}")
        if age_days is not None:
            parts.append(f"open {age_days}d")

        summary = " — ".join(parts[:2]) + ", " + ", ".join(parts[2:]) + "."
        if include_associations:
            summary += self._format_associated_objects(associated_objects)

        return AITicketAnalysis(
            summary=summary,
            urgency=urgency,
            next_action=next_action,
        )

    # ======================================================
    # TASK
    # ======================================================

    async def analyze_task(
        self,
        task: Mapping[str, Any],
        **kwargs: Any,
    ) -> AITaskAnalysis:
        props = task.get("properties") or {}
        status = (props.get("hs_task_status") or "").upper()

        if status == "COMPLETED":
            label = "Done"
            next_action = "Review outcome."
        elif status == "IN_PROGRESS":
            label = "In Progress"
            next_action = "Ensure completion."
        else:
            label = "Pending"
            next_action = "Start task."

        return AITaskAnalysis(
            summary=f"{props.get('hs_task_subject', 'Task')} — {status}",
            status_label=label,
            next_action=next_action,
        )

    # ======================================================
    # LEAD
    # ======================================================

    async def analyze_lead(
        self,
        lead: Mapping[str, Any],
        **kwargs: Any,
    ) -> AILeadAnalysis:
        props = lead.get("properties") or {}
        workspace_id = lead.get("workspace_id")
        cfg = await self._get_workspace_config(workspace_id)

        status = (props.get("hs_lead_status") or "NEW").upper()
        name = (
            f"{props.get('firstname', '')} {props.get('lastname', '')}".strip()
            or props.get("email", "Unknown Lead")
        )

        if status in {"CONNECTED", "OPEN"}:
            label = "Active"
            next_action = "Follow up within 24 hours."
        elif status in {"IN_PROGRESS"}:
            label = "In Progress"
            next_action = "Continue nurturing — check last touchpoint."
        elif status in {"UNQUALIFIED"}:
            label = "Unqualified"
            next_action = "Archive or reassign."
        else:
            label = "New"
            next_action = "Assign and make first contact."

        score = self.generate_score(props, cfg)
        lead_score = props.get("hubspotscore")

        summary = f"Lead: {name} — Status: {status}"
        if lead_score:
            summary += f", Score: {lead_score}"

        return AILeadAnalysis(
            summary=summary,
            status_label=label,
            next_action=next_action,
            score=score,
        )

    # ======================================================
    # COMMUNICATION (SMS / WhatsApp / FB Messenger)
    # ======================================================

    async def analyze_communication(
        self,
        comm: Mapping[str, Any],
        **kwargs: Any,
    ) -> AICommunicationAnalysis:
        props = comm.get("properties") or {}
        channel = props.get("hs_communication_channel_type") or "Email"
        subject = props.get("hs_communication_subject") or "Communication"

        return AICommunicationAnalysis(
            summary=f"{channel} — {subject}",
            channel=channel,
            next_action="Reply via same channel if pending.",
        )

    # ======================================================
    # APPOINTMENT
    # ======================================================

    async def analyze_appointment(
        self,
        appt: Mapping[str, Any],
        **kwargs: Any,
    ) -> AIAppointmentAnalysis:
        props = appt.get("properties") or {}
        name = props.get("hs_appointment_name") or "Appointment"
        status = (props.get("hs_appointment_status") or "SCHEDULED").upper()
        start = props.get("hs_appointment_start_time") or ""

        if status == "COMPLETED":
            label = "Completed"
            next_action = "Log outcome and follow up."
        elif status == "CANCELLED":
            label = "Cancelled"
            next_action = "Reschedule if still relevant."
        elif status == "NO_SHOW":
            label = "No Show"
            next_action = "Reach out and reschedule immediately."
        else:
            label = "Scheduled"
            next_action = "Send reminder 24h before."

        summary = f"{name} — {label}"
        if start:
            summary += f" (starts: {start[:10]})"

        return AIAppointmentAnalysis(
            summary=summary,
            status_label=label,
            next_action=next_action,
        )

    # ======================================================
    # CONVERSATION
    # ======================================================

    async def analyze_conversation(
        self,
        conv: Mapping[str, Any],
        **kwargs: Any,
    ) -> AIConversationAnalysis:
        messages = conv.get("messages", [])
        last = messages[-1].get("text", "") if messages else "No messages"

        if len(last) > 50:  # noqa: PLR2004
            last = last[:47] + "..."

        return AIConversationAnalysis(
            summary=f"Conversation {conv.get('id')} — Last: {last}",
            status=conv.get("status", "OPEN"),
            next_action="Reply if still open.",
        )

    # ======================================================
    # ENGAGEMENT
    # ======================================================

    async def analyze_engagement(
        self,
        engagement: Mapping[str, Any],
        **kwargs: Any,
    ) -> AIEngagementAnalysis:
        props = engagement.get("properties") or {}
        etype = (engagement.get("type") or "engagement").lower()

        # HubSpot v3 Engagement Property Mapping
        # Emails: hs_email_subject, hs_email_text
        # Calls: hs_call_title, hs_call_body
        # Notes: (no subject), hs_note_body
        subject = (
            props.get("hs_email_subject")
            or props.get("hs_call_title")
            or props.get("hs_subject")
            or props.get("hs_body_preview")
            or ""
        )

        body = (
            props.get("hs_email_text")
            or props.get("hs_email_html")
            or props.get("hs_call_body")
            or props.get("hs_note_body")
            or ""
        )

        if len(subject) > 80:  # noqa: PLR2004
            subject = subject[:77] + "..."

        summary = f"{etype.title()} — {subject}"
        if body and body.strip() and body not in subject:
            # Clean HTML if necessary or just truncate
            clean_body = body.strip()
            if len(clean_body) > 300:  # noqa: PLR2004
                clean_body = clean_body[:297] + "..."
            summary += f"\n\n{clean_body}"

        return AIEngagementAnalysis(
            summary=summary,
            engagement_type=etype,
            next_action="Log follow-up if required.",
        )

    # ======================================================
    # TOP ACTIONS (MULTI-TENANT SAFE)
    # ======================================================

    async def top_recommended_actions(
        self,
        objects: Sequence[Mapping[str, Any]],
        workspace_id: str | None,
    ) -> list[str]:
        cfg = await self._get_workspace_config(workspace_id)

        scored: list[tuple[int, str]] = []

        for obj in objects:
            props = obj.get("properties") or {}
            score = self.generate_score(props, cfg)
            action = self._next_action(props, metrics=None)
            scored.append((score, action))

        scored.sort(key=lambda x: x[0], reverse=True)

        unique = []
        seen = set()

        for _, action in scored:
            if action not in seen:
                unique.append(action)
                seen.add(action)
            if len(unique) == 3:  # noqa: PLR2004
                break

        return unique
