from fastapi import APIRouter

from app.integrations.oauth import OAuthService
from app.db.supabase import StorageService
from fastapi import Query, HTTPException

router = APIRouter(prefix="/slack/oauth", tags=["slack-oauth"])


@router.get("/callback")
async def slack_oauth_callback(
    code: str = Query(...),
    state: str = Query(...)
):
    """
    Slack OAuth callback.
    `state` = subscription_id
    """
    try:
        token_data = await OAuthService.exchange_slack_token(code)

        bot_token = token_data["access_token"]
        team_id = token_data["team"]["id"]

        await StorageService.save_workspace_installation(
            slack_team_id=team_id,
            slack_bot_token=bot_token,
            subscription_id=state
        )

        return {
            "status": "success",
            "message": f"Slack workspace {team_id} installed."
        }

    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))