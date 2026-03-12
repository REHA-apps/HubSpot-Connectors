import secrets

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.core.config import settings
from app.core.security.state_validator import sign_state

router = APIRouter(prefix="/slack", tags=["slack.install"])


@router.get("/install", response_class=HTMLResponse)
async def install_slack(state: str | None = None):
    raw_state = state or secrets.token_urlsafe(32)
    signed_state = sign_state(raw_state)
    oauth_url = (
        "https://slack.com/oauth/v2/authorize"
        f"?client_id={settings.SLACK_CLIENT_ID}"
        f"&scope={settings.SLACK_SCOPES_ENCODED}"
        f"&redirect_uri={settings.SLACK_REDIRECT_URI}"
        f"&state={signed_state}"
    )

    return f"""
    <html>
      <head>
        <title>Install Slack Integration</title>
        <style>
          body {{
            font-family: Arial, sans-serif;
            padding: 40px;
            max-width: 600px;
            margin: auto;
          }}
          .container {{
            text-align: center;
            margin-top: 80px;
          }}
        </style>
      </head>
      <body>
        <div class="container">
          <h1>Connect Slack</h1>
          <p>Install the Slack integration to enable HubSpot CRM search.</p>
          <a href="{oauth_url}">
            <img
              alt="Add to Slack"
              height="40"
              width="139"
              src="https://platform.slack-edge.com/img/add_to_slack.png"
              srcset="https://platform.slack-edge.com/img/add_to_slack.png 1x,
                      https://platform.slack-edge.com/img/add_to_slack@2x.png 2x"
            />
          </a>
        </div>
      </body>
    </html>
    """
