def build_contact_card(contact_data: dict, ai_summary: str):
    """
    Constructs a Slack Block Kit payload for a HubSpot Contact.
    """
    props = contact_data.get("properties", {})
    name = f"{props.get('firstname', '')} {props.get('lastname', '')}"
    email = props.get('email', 'No Email')
    company = props.get('company', 'Unknown Company')

    return {
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "🔍 HubSpot Contact Found"}
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Name:*\n{name}"},
                    {"type": "mrkdwn", "text": f"*Company:*\n{company}"}
                ]
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Email:* {email}"}
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"🤖 *AI Insight:* {ai_summary}"
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Open in HubSpot"},
                        "url": f"https://app.hubspot.com/contacts/{contact_data.get('portal_id')}/contact/{contact_data.get('id')}/",
                        "action_id": "open_contact"
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Add Note"},
                        "value": contact_data.get('id'),
                        "action_id": "add_note_modal"
                    }
                ]
            }
        ]
    }
