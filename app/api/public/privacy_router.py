# ruff: noqa: E501
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["public"])


@router.get("/privacy", response_class=HTMLResponse)
async def privacy():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Privacy Policy | REHA Connect</title>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600&display=swap"
              rel="stylesheet">
        <style>
            :root {
                --primary: #0d9488;
                --secondary: #4ade80;
                --bg: #0f172a;
                --card-bg: rgba(30, 41, 59, 0.7);
                --text: #f8fafc;
                --text-muted: #94a3b8;
            }
            body {
                font-family: 'Outfit', sans-serif;
                background-color: var(--bg);
                color: var(--text);
                display: flex;
                justify-content: center;
                padding: 4rem 2rem;
                line-height: 1.6;
            }
            .content {
                max-width: 800px;
                background: var(--card-bg);
                backdrop-filter: blur(12px);
                padding: 3rem;
                border-radius: 24px;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
            h1 { color: var(--primary); margin-bottom: 2rem; font-size: 2.5rem; }
            h2 { color: var(--secondary); margin-top: 2rem; margin-bottom: 1rem; }
            p { margin-bottom: 1rem; color: var(--text-muted); }
            ul { margin-bottom: 1.5rem; padding-left: 1.5rem; color: var(--text-muted); }
            li { margin-bottom: 0.5rem; }
        </style>
    </head>
    <body>
        <div class="content">
            <h1>Privacy Policy</h1>
            <p>Last Updated: March 2026</p>

            <h2>1. Data Collection & Usage</h2>
            <p>REHA Connect is designed with a "Privacy First" architecture. We only store the minimum
            data necessary to facilitate communication between HubSpot and Slack.</p>
            <ul>
                <li><strong>Workspace Identifiers:</strong> We store Slack Team IDs and HubSpot Portal IDs
                to route notifications correctly.</li>
                <li><strong>OAuth Tokens:</strong> Encrypted access and refresh tokens are stored securely
                to perform actions on your behalf (e.g., searching records or updating stages).</li>
                <li><strong>Sync Metadata:</strong> Limited metadata, such as Slack thread timestamps (thread_ts)
                and object IDs, are stored to enable features like thread syncing and "UnknownStage" resolution.</li>
            </ul>

            <h2>2. CRM Data Protection</h2>
            <p>We do <strong>not</strong> store your actual CRM records (Contacts, Deals, Companies) on our
            servers. All CRM data is fetched in real-time via HubSpot APIs and passed directly to Slack using
            secure protocols. Data is never cached for longer than the immediate request cycle except for
            strictly diagnostic metadata.</p>

            <h2>3. Professional Tier Features</h2>
            <p>For workspaces on the Professional tier, we process limited billing and usage data to manage
            trial periods, seat allocations, and feature access. This data is handled by our secure billing
            provider and is never shared with third parties for marketing purposes.</p>

            <h2>4. Data Retention & Deletion</h2>
            <p>You may uninstall REHA Connect at any time. Upon uninstallation, all associated OAuth
            tokens are immediately revoked and scheduled for permanent deletion from our storage services.</p>
        </div>
    </body>
    </html>
    """
