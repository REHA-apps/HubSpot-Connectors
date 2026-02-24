from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.core.exceptions import AIServiceError
from app.core.logging import get_logger
from app.utils.helpers import normalize_object_type
from app.utils.parsers import to_int

logger = get_logger("ai.service")


# Scoring Constants
VISIT_THRESHOLD_MODERATE = 5
VISIT_THRESHOLD_HIGH = 10
VISIT_THRESHOLD_VERY_HIGH = 15

SCORE_HIGH_VISITS = 40
SCORE_QUALIFIED_LIFECYCLE = 30
SCORE_HAS_COMPANY = 10
SCORE_HAS_EMAIL = 10
MAX_SCORE = 100

QUALIFIED_STAGES = {"marketingqualifiedlead", "salesqualifiedlead"}


# AI analysis models
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
class AIThreadSummary:
    summary: str
    key_points: list[str]
    sentiment: str


# Core AI Service
class AIService:
    """Core AI service providing deterministic rules for HubSpot object analysis.

    Utilizes scoring algorithms to evaluate contact engagement and quality,
    generating actionable insights and next-best-action recommendations.
    Supports intent detection for natural language queries.
    """

    def __init__(self, corr_id: str) -> None:
        self.deal_ai = AIDealService()
        self.company_ai = AICompanyService()
        self.ticket_ai = AITicketService()
        self.task_ai = AITaskService()

    def set_corr_id(self, corr_id: str) -> None:
        """DEPRECATED: No longer needed with context-aware logging."""
        pass

    # -----------------------------------------------------
    # Normalization
    # -----------------------------------------------------
    def normalize_contact_props(self, props: dict[str, Any]) -> dict[str, Any]:
        """Normalize numeric fields and ensure consistent types.

        Args:
            props (dict[str, Any]): Raw HubSpot contact properties.

        Returns:
            dict[str, Any]: Normalized properties with safe integer defaults.

        """
        numeric_fields = [
            "hs_analytics_num_visits",
            "num_associated_deals",
            "hs_lifecyclestage_lead_score",
        ]

        for field in numeric_fields:
            props[field] = to_int(props.get(field)) or 0

        return props

    # -----------------------------------------------------
    # Feature extraction
    # -----------------------------------------------------
    def _extract_features(self, props: Mapping[str, Any]) -> dict[str, Any]:
        """Extract normalized, typed features for scoring.

        Args:
            props (Mapping[str, Any]): Normalized contact properties.

        Returns:
            dict[str, Any]: A dictionary containing extracted features (visits, etc).

        """
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
        """Generates a human-readable insight based on contact engagement.

        Args:
            contact (Mapping[str, Any]): The HubSpot contact object.

        Returns:
            str: A descriptive insight string.

        """
        props = self.normalize_contact_props(contact.get("properties") or {})

        firstname = props.get("firstname") or "This contact"
        company = props.get("company") or "Unknown Company"
        visits = props.get("hs_analytics_num_visits", 0)

        insight = f"💡 {firstname} works at {company}."

        if visits > VISIT_THRESHOLD_MODERATE:
            insight += f" They are highly engaged with {visits} visits."
        else:
            insight += " Engagement is low."

        return insight

    # -----------------------------------------------------
    # Scoring
    # -----------------------------------------------------
    def generate_score(self, props: Mapping[str, Any]) -> int:
        """Calculates a priority score for the contact.

        Args:
            props (Mapping[str, Any]): Normalized contact properties.

        Returns:
            int: A score between 0 and 100.

        """
        f = self._extract_features(props)
        score = 0

        if f["visits"] > VISIT_THRESHOLD_HIGH:
            score += SCORE_HIGH_VISITS

        if f["lifecycle"] in QUALIFIED_STAGES:
            score += SCORE_QUALIFIED_LIFECYCLE

        if f["has_company"]:
            score += SCORE_HAS_COMPANY

        if f["has_email"]:
            score += SCORE_HAS_EMAIL

        return min(score, MAX_SCORE)

    def generate_score_reason(self, props: Mapping[str, Any], score: int) -> str:
        """Generates a human-readable explanation for the calculated score.

        Args:
            props (Mapping[str, Any]): Normalized contact properties.
            score (int): The calculated score.

        Returns:
            str: A comma-separated list of scoring factors.

        """
        f = self._extract_features(props)
        reasons: list[str] = []

        if f["visits"] > VISIT_THRESHOLD_HIGH:
            reasons.append("High engagement")
        elif f["visits"] > VISIT_THRESHOLD_MODERATE:
            reasons.append("Moderate engagement")
        else:
            reasons.append("Low engagement")

        if f["lifecycle"] in QUALIFIED_STAGES:
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
        """Determines the single most important next action for this contact.

        Args:
            props (Mapping[str, Any]): Normalized contact properties.

        Returns:
            str: A recommended action string with an emoji.

        """
        f = self._extract_features(props)

        if f["lifecycle"] == "lead" and f["visits"] > VISIT_THRESHOLD_MODERATE:
            return "📞 Reach out — this lead is warming up."

        if f["lifecycle"] == "marketingqualifiedlead":
            return "🤝 Hand off to sales — strong MQL."

        if f["lifecycle"] == "salesqualifiedlead":
            return "📅 Schedule a discovery call."

        if f["visits"] > VISIT_THRESHOLD_VERY_HIGH:
            return "🔥 High engagement — follow up immediately."

        return "📝 Add a note or send a follow-up email."

    def generate_next_action(self, props: Mapping[str, Any]) -> str:
        return self.next_best_action(props)

    def generate_next_action_reason(self, props: Mapping[str, Any]) -> str:
        f = self._extract_features(props)

        if f["lifecycle"] == "lead" and f["visits"] > VISIT_THRESHOLD_MODERATE:
            return "Lead is warming up"
        if f["lifecycle"] == "marketingqualifiedlead":
            return "Strong MQL"
        if f["lifecycle"] == "salesqualifiedlead":
            return "SQL ready for call"
        if f["visits"] > VISIT_THRESHOLD_VERY_HIGH:
            return "High engagement"

        return "General follow-up recommended"

    # -----------------------------------------------------
    # Summary + reasoning
    # -----------------------------------------------------
    def generate_summary(self, props: Mapping[str, Any]) -> str:
        """Generates a concise summary of the contact and their company.

        Args:
            props (Mapping[str, Any]): Normalized contact properties.

        Returns:
            str: A summary sentence.

        """
        f = self._extract_features(props)
        firstname = f["props"].get("firstname") or "This contact"
        company = f["props"].get("company") or "Unknown company"

        return f"{firstname} from {company} has {f['visits']} recent visits."

    def generate_reasoning(self, props: Mapping[str, Any]) -> str:
        """Provides detailed technical reasoning for the AI's conclusions.

        Args:
            props (Mapping[str, Any]): Normalized contact properties.

        Returns:
            str: A detailed string combining multiple engagement factors.

        """
        f = self._extract_features(props)
        reasons: list[str] = []

        if f["visits"] > VISIT_THRESHOLD_HIGH:
            reasons.append("High engagement based on recent visits")
        elif f["visits"] > VISIT_THRESHOLD_MODERATE:
            reasons.append("Moderate engagement")
        else:
            reasons.append("Low engagement")

        if f["lifecycle"] in QUALIFIED_STAGES:
            reasons.append("Qualified lifecycle stage")

        if f["has_company"]:
            reasons.append("Associated with a company")

        if f["has_email"]:
            reasons.append("Valid email present")

        return ". ".join(reasons) + "."

    # Analysis entry points
    async def analyze_polymorphic(
        self, obj: Mapping[str, Any], object_type: str
    ) -> (
        AIContactAnalysis
        | AICompanyAnalysis
        | AIDealAnalysis
        | AITicketAnalysis
        | AITaskAnalysis
        | AITicketAnalysis
        | AITaskAnalysis
        | AIConversationAnalysis
    ):
        """Standardized entry point for analyzing any HubSpot object.

        Args:
            obj (Mapping[str, Any]): The raw HubSpot object data.
            object_type (str): The logical type of the object (e.g., "contact", "deal").

        Returns:
            Union[AIContactAnalysis, ...]: A type-specific analysis object.

        """
        try:
            # 1. Handle None or non-mapping inputs gracefully
            if not isinstance(obj, Mapping):
                logger.warning(
                    "Invalid input for analysis: %s (type=%s)", obj, type(obj)
                )
                # Return a safe fallback with "unavailable" insight
                return AIContactAnalysis(
                    insight="Analysis unavailable due to invalid input.",
                    score=0,
                    score_reason="Invalid input.",
                    next_best_action="Check input data format.",
                    next_action="Review log for details.",
                    next_action_reason="Input data was not a valid mapping.",
                    summary="Analysis failed.",
                    reasoning="The provided object was None or not a dictionary.",
                )

            normalized_type = normalize_object_type(object_type)

            handler_map = {
                "contact": self.analyze_contact,
                "lead": self.analyze_contact,
                "company": self.analyze_company,
                "deal": self.analyze_deal,
                "ticket": self.analyze_ticket,
                "task": self.analyze_task,
                "conversation": self.analyze_conversation,
                "thread": self.analyze_conversation,
            }

            handler = handler_map.get(normalized_type)
            if not handler:
                logger.warning(
                    "Unknown object_type=%s, falling back to contact analysis",
                    object_type,
                )
                handler = self.analyze_contact

            return await handler(obj)
        except AIServiceError as exc:
            logger.error("AI service failure for %s: %s", object_type, exc)
            raise
        except Exception as exc:
            logger.error("Unexpected AI analysis error for %s: %s", object_type, exc)
            raise AIServiceError(f"AI analysis failed: {str(exc)}") from exc

    async def analyze_contact(self, obj: Mapping[str, Any]) -> AIContactAnalysis:
        """Performs deep analysis on a Contact object.

        Args:
            obj (Mapping[str, Any]): The HubSpot contact object.

        Returns:
            AIContactAnalysis: Analysis containing score, insights, and actions.

        """
        props = self.normalize_contact_props(dict(obj.get("properties") or {}))
        score = self.generate_score(props)

        return AIContactAnalysis(
            insight=self.generate_contact_insight(obj),
            score=score,
            score_reason=self.generate_score_reason(props, score),
            next_best_action=self.next_best_action(props),
            next_action=self.generate_next_action(props),
            next_action_reason=self.generate_next_action_reason(props),
            summary=self.generate_summary(props),
            reasoning=self.generate_reasoning(props),
        )

    async def analyze_deal(self, deal: Mapping[str, Any]) -> AIDealAnalysis:
        """Analyzes a Deal using specialized logic.

        Args:
            deal (Mapping[str, Any]): The HubSpot deal object.

        Returns:
            AIDealAnalysis: Structured deal insights.

        """
        return self.deal_ai.analyze_deal(deal)

    async def analyze_company(self, company: Mapping[str, Any]) -> AICompanyAnalysis:
        """Analyzes a Company using specialized logic.

        Args:
            company (Mapping[str, Any]): The HubSpot company object.

        Returns:
            AICompanyAnalysis: Structured company health insights.

        """
        return self.company_ai.analyze_company(company)

    async def analyze_lead(self, lead: Mapping[str, Any]) -> AIContactAnalysis:
        """Leads use Contact analysis logic."""
        return await self.analyze_contact(lead)

    async def analyze_ticket(self, ticket: Mapping[str, Any]) -> AITicketAnalysis:
        """Analyzes a Ticket using specialized logic."""
        return self.ticket_ai.analyze_ticket(ticket)

    async def analyze_task(self, task: Mapping[str, Any]) -> AITaskAnalysis:
        """Analyzes a Task using specialized logic."""
        return self.task_ai.analyze_task(task)

    async def analyze_conversation(
        self, thread: Mapping[str, Any]
    ) -> AIConversationAnalysis:
        """Analyzes a Conversation Thread."""
        # Thread object: id, status, messages (list), etc.
        t_id = thread.get("id")
        status = thread.get("status") or "OPEN"
        messages = thread.get("messages", [])
        msg_count = len(messages)

        last_msg = messages[0].get("text", "") if messages else "No messages"
        if len(last_msg) > 50:  # noqa: PLR2004
            last_msg = last_msg[:47] + "..."

        summary = (
            f"Conversation #{t_id} ({status}) • {msg_count} messages. Last: {last_msg}"
        )

        next_action = (
            "Reply to visitor." if status != "CLOSED" else "Review closed conversation."
        )

        return AIConversationAnalysis(
            summary=summary,
            status=status,
            next_action=next_action,
        )

    # -----------------------------------------------------
    # Multi-object summarization
    # -----------------------------------------------------
    def summarize_results(self, objects: Sequence[Mapping[str, Any]]) -> str:
        """Generates a summary string for a collection of search results.

        Args:
            objects (Sequence[Mapping[str, Any]]): A list of HubSpot records.

        Returns:
            str: A formatted summary string for Slack.

        """
        if not objects:
            return "No matching HubSpot records found."

        contacts = sum(1 for o in objects if "firstname" in (o.get("properties") or {}))
        leads = sum(
            1
            for o in objects
            if (o.get("properties") or {}).get("lifecyclestage") == "lead"
        )
        deals = sum(1 for o in objects if "dealname" in (o.get("properties") or {}))

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

        actions: list[tuple[int, str]] = []

        for obj in objects:
            props = self.normalize_contact_props(dict(obj.get("properties") or {}))
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
            if len(top) == 3:  # noqa: PLR2004
                break

        return top

    # -----------------------------------------------------
    # Intent detection
    # -----------------------------------------------------
    # -----------------------------------------------------
    # Thread Summarization
    # -----------------------------------------------------
    async def summarize_thread(self, messages: list[dict[str, Any]]) -> AIThreadSummary:
        """Description:
            Generates an AI-powered summary of a Slack thread.
            Utilizes heuristics for key point extraction and sentiment analysis.

        Args:
            messages (list[dict[str, Any]]): List of Slack message dictionaries.

        Returns:
            AIThreadSummary: Structured summary with key points and sentiment.

        """
        if not messages:
            return AIThreadSummary(
                summary="No messages to summarize.", key_points=[], sentiment="Neutral"
            )

        # 1. Extract texts
        texts = [m.get("text", "") for m in messages if m.get("text")]
        combined_text = " ".join(texts)

        # 2. Heuristic: Determine Sentiment
        positive_words = {
            "good",
            "great",
            "excellent",
            "fixed",
            "resolved",
            "thanks",
            "happy",
        }
        negative_words = {
            "bug",
            "error",
            "failed",
            "broken",
            "issue",
            "problem",
            "urgent",
        }

        pos_count = sum(1 for word in positive_words if word in combined_text.lower())
        neg_count = sum(1 for word in negative_words if word in combined_text.lower())

        sentiment = "Neutral"
        if pos_count > neg_count:
            sentiment = "Positive"
        elif neg_count > pos_count:
            sentiment = "Negative"

        # 3. Heuristic: Extract Key Points (Messages with question marks or
        # exclamation marks)
        key_points = []
        for text in texts:
            if "?" in text or "!" in text or len(text) > 100:  # noqa: PLR2004
                clean_point = text.strip().replace("\n", " ")
                MAX_POINT_LEN = 80
                key_points.append(
                    clean_point[:MAX_POINT_LEN] + "..."
                    if len(clean_point) > MAX_POINT_LEN
                    else clean_point
                )

        # 4. Generate Summary
        msg_count = len(messages)
        MAX_FIRST_MSG_LEN = 100
        first_msg = (
            texts[0][:MAX_FIRST_MSG_LEN] + "..."
            if texts and len(texts[0]) > MAX_FIRST_MSG_LEN
            else (texts[0] if texts else "")
        )
        summary_text = (
            f"Thread with {msg_count} messages starting with: '{first_msg}'. "
            f"Overall sentiment appears {sentiment}."
        )

        return AIThreadSummary(
            summary=summary_text,
            key_points=key_points[:5],
            sentiment=sentiment,
        )

    def detect_intent(self, query: str) -> str:
        """Detects the primary CRM object intent from a natural language query.

        Args:
            query (str): The user's query string.

        Returns:
            str: The logical object type detected (e.g., "deal", "ticket").

        """
        q = query.lower()

        intent_map = {
            "deal": ["deal", "renewal", "contract", "pipeline", "amount"],
            "lead": ["lead", "mql", "sql", "prospect"],
            "ticket": ["ticket", "issue", "bug", "support", "incident"],
            "task": ["task", "todo", "follow-up", "reminder", "action item"],
        }

        for intent, keywords in intent_map.items():
            if any(k in q for k in keywords):
                return intent

        return "contact"


# Deal-specific AI Service
class AIDealService:
    def analyze_deal(self, deal: Mapping[str, Any]) -> AIDealAnalysis:
        """Provides structural analysis for HubSpot Deals.

        Args:
            deal (Mapping[str, Any]): Raw deal data.

        Returns:
            AIDealAnalysis: Summary, risk assessment, and next actions.

        """
        props = deal.get("properties") or {}
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


# Company-specific AI Service
class AICompanyService:
    def analyze_company(self, company: Mapping[str, Any]) -> AICompanyAnalysis:
        """Analyzes company health based on associated records.

        Args:
            company (Mapping[str, Any]): Raw company data.

        Returns:
            AICompanyAnalysis: Health status and strategic next actions.

        """
        props = company.get("properties") or {}
        name = props.get("name") or "This company"
        num_contacts = int(props.get("num_associated_contacts", 0) or 0)
        num_deals = int(props.get("num_associated_deals", 0) or 0)

        summary = f"{name} with {num_contacts} contacts and {num_deals} deals."

        if num_deals == 0:
            health = "Dormant"
            next_action = "Identify opportunities and create first deal."
        if num_deals == 0:
            health = "Dormant"
            next_action = "Identify opportunities and create first deal."
        elif num_deals > VISIT_THRESHOLD_MODERATE:
            health = "Strategic"
            next_action = "Review account plan and upsell opportunities."
        else:
            health = "Active"
            next_action = "Schedule an account review."

        return AICompanyAnalysis(
            summary=summary, health=health, next_action=next_action
        )


# Ticket-specific AI Service
class AITicketService:
    def analyze_ticket(self, ticket: Mapping[str, Any]) -> AITicketAnalysis:
        """Evaluates ticket urgency and assignment needs.

        Args:
            ticket (Mapping[str, Any]): Raw ticket data.

        Returns:
            AITicketAnalysis: Urgency and triage recommendations.

        """
        props = ticket.get("properties") or {}
        subject = props.get("subject") or "This ticket"
        priority = (props.get("hs_ticket_priority") or "").upper()
        stage = props.get("hs_pipeline_stage") or "Unknown"

        summary = f"{subject} — Priority: {priority or 'Unset'}, Stage: {stage}"

        if priority == "HIGH":
            urgency = "Critical"
            next_action = "Assign immediately and begin resolution."
        elif priority == "MEDIUM":
            urgency = "Moderate"
            next_action = "Triage and assign to appropriate team."
        else:
            urgency = "Low"
            next_action = "Review during next sprint planning."

        return AITicketAnalysis(
            summary=summary, urgency=urgency, next_action=next_action
        )


# Task-specific AI Service
class AITaskService:
    def analyze_task(self, task: Mapping[str, Any]) -> AITaskAnalysis:
        """Assesses task status and priority.

        Args:
            task (Mapping[str, Any]): Raw task data.

        Returns:
            AITaskAnalysis: Status label and immediate next actions.

        """
        props = task.get("properties") or {}
        subject = props.get("hs_task_subject") or "This task"
        status = (props.get("hs_task_status") or "NOT_STARTED").upper()
        priority = (props.get("hs_task_priority") or "").upper()

        summary = f"{subject} — Status: {status}, Priority: {priority or 'Unset'}"

        if status == "COMPLETED":
            status_label = "Done"
            next_action = "Archive or review outcomes."
        elif status == "IN_PROGRESS":
            status_label = "In Progress"
            next_action = "Check for blockers and ensure timely completion."
        elif status == "WAITING":
            status_label = "Waiting"
            next_action = "Follow up with the responsible party."
        else:
            status_label = "Not Started"
            next_action = "Prioritize and assign to a team member."

        return AITaskAnalysis(
            summary=summary, status_label=status_label, next_action=next_action
        )
