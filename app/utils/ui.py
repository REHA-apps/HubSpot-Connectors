from __future__ import annotations

from html import escape

from fastapi.responses import HTMLResponse


def render_success_page(
    title: str,
    message: str,
    workspace_id: str,
    primary_color: str = "#ff5c35",  # HubSpot Orange as default
    secondary_color: str = "#4a154b",  # Slack Purple
) -> HTMLResponse:
    """Description:
        Renders a premium, branded success page for OAuth completion.

    Args:
        title (str): Page title and header.
        message (str): Succinct success message.
        workspace_id (str): Reference ID for the user.
        primary_color (str): Primary accent color (HSL/Hex).
        secondary_color (str): Secondary accent color.

    Returns:
        HTMLResponse: Styled HTML content.

    """
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title}</title>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600&display=swap"
              rel="stylesheet">
        <style>
            :root {{
                --primary: {primary_color};
                --secondary: {secondary_color};
                --bg: #0f172a;
                --card-bg: rgba(30, 41, 59, 0.7);
                --text: #f8fafc;
                --text-muted: #94a3b8;
            }}

            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}

            body {{
                font-family: 'Outfit', sans-serif;
                background-color: var(--bg);
                background-image:
                    radial-gradient(circle at 20% 20%, rgba(255, 92, 53, 0.05) 0%,
                                    transparent 40%),
                    radial-gradient(circle at 80% 80%, rgba(74, 21, 75, 0.05) 0%,
                                    transparent 40%);
                color: var(--text);
                height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                overflow: hidden;
            }}

            .card {{
                background: var(--card-bg);
                backdrop-filter: blur(12px);
                border: 1px solid rgba(255, 255, 255, 0.1);
                padding: 3rem;
                border-radius: 24px;
                width: 100%;
                max-width: 480px;
                text-align: center;
                box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
                animation: slideUp 0.6s cubic-bezier(0.16, 1, 0.3, 1);
            }}

            @keyframes slideUp {{
                from {{ opacity: 0; transform: translateY(20px); }}
                to {{ opacity: 1; transform: translateY(0); }}
            }}

            .icon-wrapper {{
                width: 80px;
                height: 80px;
                background: linear-gradient(135deg, var(--primary), var(--secondary));
                border-radius: 20px;
                margin: 0 auto 2rem;
                display: flex;
                align-items: center;
                justify-content: center;
                box-shadow: 0 10px 20px -5px var(--primary);
                animation: pulse 2s infinite;
            }}

            @keyframes pulse {{
                0% {{ transform: scale(1);
                      box-shadow: 0 10px 20px -5px var(--primary); }}
                50% {{ transform: scale(1.05);
                       box-shadow: 0 15px 30px -5px var(--primary); }}
                100% {{ transform: scale(1);
                        box-shadow: 0 10px 20px -5px var(--primary); }}
            }}

            .check-icon {{
                color: white;
                font-size: 40px;
            }}

            h1 {{
                font-size: 2rem;
                font-weight: 600;
                margin-bottom: 1rem;
                letter-spacing: -0.02em;
            }}

            p {{
                color: var(--text-muted);
                line-height: 1.6;
                margin-bottom: 2rem;
            }}

            .workspace-badge {{
                display: inline-block;
                padding: 0.5rem 1rem;
                background: rgba(255, 255, 255, 0.05);
                border-radius: 99px;
                font-size: 0.875rem;
                color: var(--text-muted);
                border: 1px solid rgba(255, 255, 255, 0.1);
            }}

            .workspace-id {{
                color: var(--primary);
                font-weight: 600;
            }}

            .footer-links {{
                margin-top: 3rem;
                display: flex;
                gap: 1.5rem;
                justify-content: center;
            }}

            .footer-links a {{
                color: var(--text-muted);
                text-decoration: none;
                font-size: 0.8125rem;
                transition: color 0.2s;
            }}

            .footer-links a:hover {{
                color: var(--text);
            }}

            .confetti {{
                position: absolute;
                top: 0; left: 0; width: 100%; height: 100%;
                pointer-events: none;
                z-index: -1;
            }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="icon-wrapper">
                <span class="check-icon">✓</span>
            </div>
            <h1>{escape(title)}</h1>
            <p>{escape(message)}</p>

            <div class="workspace-badge">
                Workspace ID: <span class="workspace-id">{workspace_id}</span>
            </div>

            <!-- <div class="footer-links">
                <a href="#">Documentation</a>
                <a href="#">Support</a>
                <a href="#">Dashboard</a>
            </div> -->
        </div>

        <script>
            // Simple micro-animation for the icon
            document.querySelector('.icon-wrapper').addEventListener(
                'mouseover', () => {{
                document.querySelector('.icon-wrapper').style.transform =
                    'rotate(5deg) scale(1.1)';
            }});
            document.querySelector('.icon-wrapper').addEventListener(
                'mouseout', () => {{
                document.querySelector('.icon-wrapper').style.transform =
                    'rotate(0) scale(1)';
            }});
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)
