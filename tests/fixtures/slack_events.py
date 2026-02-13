# tests/fixtures/slack_events.py
from collections.abc import Mapping
from typing import Any

import pytest


@pytest.fixture
def slack_slash_command() -> Mapping[str, Any]:
    return {
        "token": "verification-token",
        "team_id": "T12345",
        "team_domain": "example",
        "channel_id": "C12345",
        "channel_name": "general",
        "user_id": "U12345",
        "user_name": "john",
        "command": "/hs",
        "text": "email=test@example.com",
        "response_url": "https://hooks.slack.com/commands/123",
    }


@pytest.fixture
def slack_event_message() -> Mapping[str, Any]:
    return {
        "type": "event_callback",
        "team_id": "T12345",
        "event": {
            "type": "message",
            "channel": "C12345",
            "user": "U12345",
            "text": "Hello world",
            "ts": "123456.789",
        },
    }


@pytest.fixture
def slack_interactive_action() -> Mapping[str, Any]:
    return {
        "type": "block_actions",
        "user": {"id": "U12345"},
        "team": {"id": "T12345"},
        "channel": {"id": "C12345"},
        "actions": [
            {
                "action_id": "open_contact",
                "value": "12345",
            }
        ],
        "response_url": "https://hooks.slack.com/actions/123",
    }
