# app/api/slack/oauth_router.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, Depends

from app.core.logging import CorrelationAdapter, get_logger, get_corr_id
from app.services.integration_service import IntegrationService
from app.utils.constants import ErrorCode

router = APIRouter(prefix="/slack/oauth", tags=["slack-oauth"])
logger = get_logger("slack.oauth")


@router.get("/callback")
async def slack_oauth_callback(
    request: Request,
    code: str = Query(...),
    state: str | None = Query(default=None),
    corr_id: str = Depends(get_corr_id),
) -> dict[str, str]:
    """Slack OAuth callback."""
    log = CorrelationAdapter(logger, corr_id)

    log.info("Received Slack OAuth callback code=%s state=%s", code, state)

    # Optional: handle Slack OAuth errors
    error = request.query_params.get("error")
    if error:
        log.warning("Slack OAuth error=%s", error)
        raise HTTPException(
            status_code=ErrorCode.BAD_REQUEST, detail=f"Slack OAuth error: {error}"
        )

    try:
        integration_service = IntegrationService(corr_id)

        workspace_id = await integration_service.handle_slack_oauth_callback(
            code=code,
            state=state,
        )

        return {
            "status": "success",
            "message": "Slack connected successfully.",
            "workspace_id": workspace_id,
        }

    except HTTPException:
        raise

    except Exception as exc:
        log.error("Slack OAuth callback failed: %s", exc)
        raise HTTPException(
            status_code=ErrorCode.INTERNAL_ERROR, detail="Slack OAuth failed"
        ) from exc
