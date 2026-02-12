from typing import Dict, Any

def build_contact_card(contact_data: Dict[str, Any], ai_summary: str) -> list[Dict[str, Any]]:
    """Constructs a Slack Block Kit payload for a HubSpot Contact.
    
    Args:
        contact_data: The raw contact data from HubSpot.
        ai_summary: A short AI-generated summary/insight about the contact.
        
    Returns:
        A list of dictionaries representing the Slack Block Kit message.
    """
    props = contact_data.get("properties", {})
    firstname = props.get('firstname', '')
    lastname = props.get('lastname', '')
    name = f"{firstname} {lastname}".strip() or "Unknown Name"
    email = props.get('email', 'No Email')
    company = props.get('company', 'Unknown Company')

    return [
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
                    "value": str(contact_data.get('id')),
                    "action_id": "add_note_modal"
                }
            ]
        }
    ]
