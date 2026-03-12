# ruff: noqa: E501
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["public"])


@router.get("/terms", response_class=HTMLResponse)
async def terms():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Terms of Service | REHA Connect</title>
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
            <h1>Terms of Service</h1>
            <p>Last Updated: March 2026</p>

            <h2>1. Service Description</h2>
            <p>REHA Connect provides a bridge between HubSpot CRM and Slack. Our core features include:</p>
            <ul>
                <li><strong>Object Resolution:</strong> Viewing and interacting with HubSpot Contacts,
                Deals, and Companies directly from Slack.</li>
                <li><strong>Workflow Automation:</strong> Real-time notifications for CRM events
                (e.g., deal stage changes, ticket creation).</li>
                <li><strong>Collaboration Tools:</strong> Creating and managing HubSpot
                Tickets and Tasks within Slack channels.</li>
            </ul>

            <h2>2. Access & Permissions</h2>
            <p>By installing REHA Connect, you grant the application permission to access
            specific scopes within your Slack workspace and HubSpot portal. These
            permissions are used strictly to perform actions initiated by your users or
            to send configured notifications.</p>

            <h2>3. Usage & Responsibility</h2>
            <p>Users are responsible for ensuring their use of REHA Connect complies with
            their own internal data governance and compliance policies. We provide the
            service as-is and are not responsible for any misuse of data by authorized
            users within your workspace.</p>

            <h2>4. Termination</h2>
            <p>We reserve the right to suspend or terminate access to the service for any
            workspace that violates these terms or engages in activities deemed harmful
            to the system's stability or integrity.</p>
        </div>
    </body>
    </html>
    """
