from __future__ import annotations

from typing import Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    Response,
)

from app.core.dependencies import get_integration_service
from app.core.exceptions import IntegrationNotFoundError
from app.core.logging import get_corr_id, get_logger
from app.core.security.slack_signature import (
    slack_signature_required,
)
from app.domains.crm.integration_service import IntegrationService
from app.domains.messaging.slack.service import SlackMessagingService
from app.utils.constants import ErrorCode

router = APIRouter(prefix="/slack", tags=["slack-events"])
logger = get_logger("slack.events")

# Simple in-memory de-duplication for unfurls (channel:ts)
LATEST_UNFURLS: set[str] = set()
DEDUPE_LIMIT = 100


@router.post(
    "/events",
    dependencies=[Depends(slack_signature_required)],
)
async def slack_events(  # noqa: PLR0911, PLR0912, PLR0915
    request: Request,
    background_tasks: BackgroundTasks,
    corr_id: str = Depends(get_corr_id),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> Any:
    """Handles Slack Events API callbacks.
    Supports:
    - url_verification
    - app_uninstalled
    """
    try:
        payload = await request.json()
        logger.info("Received Slack event: type=%s", payload.get("type"))
    except Exception as exc:
        logger.error("Failed to parse Slack event payload: %s", exc)
        raise HTTPException(
            status_code=ErrorCode.BAD_REQUEST, detail="Invalid JSON payload"
        )

    # ---------------------------------------------------------
    # Slack URL verification challenge
    # ---------------------------------------------------------
    if payload.get("type") == "url_verification":
        challenge = payload["challenge"]
        logger.info("Responding to Slack challenge")
        return Response(content=challenge, media_type="text/plain")

    # ---------------------------------------------------------
    # Normal event handling
    # ---------------------------------------------------------
    event = payload.get("event", {})
    event_type = event.get("type")
    team_id = payload.get("team_id")

    logger.info("Slack event type=%s team_id=%s", event_type, team_id)

    # Handle uninstall event
    if event_type == "app_uninstalled":
        if not team_id:
            logger.error("Missing team_id in uninstall event")
            return {"ok": False}

        logger.info("Processing Slack uninstall for team_id=%s", team_id)

        try:
            workspace_id = await integration_service.resolve_workspace(team_id)
            await integration_service.uninstall_slack(workspace_id)
            logger.info("Slack integration removed for workspace_id=%s", workspace_id)
        except IntegrationNotFoundError:
            logger.info(
                "Slack integration already removed or not found (idempotent skip)"
            )
        except Exception as exc:
            logger.warning("Slack uninstall failed: %s", exc)

        return {"ok": True}

    # Handle link_shared event
    if event_type == "link_shared":
        links = event.get("links", [])
        channel = event.get("channel")
        ts = event.get("message_ts")

        if not links or not channel or not ts:
            return {"ok": True}

        # Deduplication check
        dedupe_key = f"{channel}:{ts}"
        if dedupe_key in LATEST_UNFURLS:
            logger.info("Skipping duplicate unfurl for %s", dedupe_key)
            return {"ok": True}
        _mark_unfurled(dedupe_key)

        logger.info(
            "Processing Slack link_shared event: channel=%s, ts=%s, links_count=%d",
            channel,
            ts,
            len(links),
        )

        workspace_id = await integration_service.resolve_workspace(team_id)
        integration = await integration_service.get_integration_by_slack_team_id(
            team_id
        )

        if not integration:
            logger.error("No integration found for unfurl")
            return {"ok": True}

        messaging_service = SlackMessagingService(
            corr_id=corr_id,
            integration_service=integration_service,
            slack_integration=integration,
        )

        background_tasks.add_task(
            messaging_service.handle_link_shared,
            workspace_id=workspace_id,
            channel=channel,
            ts=ts,
            links=links,
        )
        return {"ok": True}

    if event_type == "message":
        subtype = event.get("subtype")
        thread_ts = event.get("thread_ts")
        ts = event.get("ts")
        blocks = event.get("blocks")

        if blocks:
            # Link Sniffing Workaround: Extract links and trigger unfurl manually
            extracted_urls = _extract_links_from_blocks(blocks)
            hubspot_links = [{"url": u} for u in extracted_urls if "hubspot.com" in u]

            if hubspot_links and not event.get("bot_id"):
                # Deduplication check
                dedupe_key = f"{event.get('channel')}:{ts}"
                if dedupe_key in LATEST_UNFURLS:
                    logger.info("Skipping duplicate sniffed unfurl for %s", dedupe_key)
                    return {"ok": True}
                _mark_unfurled(dedupe_key)

                logger.info(
                    "Found %d HubSpot links in message blocks", len(hubspot_links)
                )
                try:
                    workspace_id = await integration_service.resolve_workspace(team_id)
                    integration = (
                        await integration_service.get_integration_by_slack_team_id(
                            team_id
                        )
                    )
                    if integration:
                        messaging_service = SlackMessagingService(
                            corr_id=corr_id,
                            integration_service=integration_service,
                            slack_integration=integration,
                        )
                        background_tasks.add_task(
                            messaging_service.handle_link_shared,
                            workspace_id=workspace_id,
                            channel=event.get("channel"),
                            ts=ts,
                            links=hubspot_links,
                        )
                except Exception as exc:
                    logger.error("Failed to trigger manual unfurl: %s", exc)

        # Threaded reply sync
        if (
            subtype is None
            and not event.get("bot_id")
            and thread_ts
            and ts
            and thread_ts != ts
        ):
            text = event.get("text", "")
            user = event.get("user", "")
            channel = event.get("channel", "")

            logger.info(
                "Processing threaded reply in channel=%s thread_ts=%s",
                channel,
                thread_ts,
            )

            integration = await integration_service.get_integration_by_slack_team_id(
                team_id
            )
            if integration:
                messaging_service = SlackMessagingService(
                    corr_id=corr_id,
                    integration_service=integration_service,
                    slack_integration=integration,
                )

                background_tasks.add_task(
                    messaging_service.handle_threaded_reply,
                    workspace_id=integration.workspace_id,
                    channel=channel,
                    thread_ts=thread_ts,
                    message_ts=str(ts),
                    text=text,
                    user=user,
                )

    if event_type == "app_home_opened":
        user_id = event.get("user")
        if user_id:
            logger.info(
                "Processing app_home_opened for user=%s team_id=%s", user_id, team_id
            )
            integration = await integration_service.get_integration_by_slack_team_id(
                team_id
            )
            if integration:
                messaging_service = SlackMessagingService(
                    corr_id=corr_id,
                    integration_service=integration_service,
                    slack_integration=integration,
                )
                background_tasks.add_task(
                    messaging_service.handle_app_home_opened,
                    user_id=user_id,
                )

    return {"ok": True}


def _extract_links_from_blocks(blocks: list[dict[str, Any]]) -> list[str]:
    """Recursively extract all type: link URLs from Slack blocks."""
    links = []

    def traverse(item: Any):
        if isinstance(item, list):
            for i in item:
                traverse(i)
        elif isinstance(item, dict):
            if item.get("type") == "link" and item.get("url"):
                links.append(item["url"])
            for value in item.values():
                traverse(value)

    traverse(blocks)
    return list(set(links))


def _mark_unfurled(key: str):
    """Mark a message as unfurled and maintain cache size."""
    LATEST_UNFURLS.add(key)
    if len(LATEST_UNFURLS) > DEDUPE_LIMIT:
        overflow = list(LATEST_UNFURLS)[-DEDUPE_LIMIT:]
        LATEST_UNFURLS.clear()
        LATEST_UNFURLS.update(overflow)
