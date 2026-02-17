from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from app.core.config import settings
import secrets

router = APIRouter(prefix="/install", tags=["slack.install"])

@router.get("/slack", response_class=HTMLResponse)
async def install_slack():
    state = secrets.token_urlsafe(32)
    oauth_url = (
        "https://slack.com/oauth/v2/authorize"
        f"?client_id={settings.SLACK_CLIENT_ID}"
        f"&scope={settings.SLACK_SCOPES_ENCODED}"
        f"&redirect_uri={settings.SLACK_REDIRECT_URI}"
        f"&state={state}"
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
              srcset="https://platform.slack-edge.com/img/add_to_slack.png 1x, https://platform.slack-edge.com/img/add_to_slack@2x.png 2x"
            />
          </a>
        </div>
      </body>
    </html>
    """
