from enum import IntEnum
from typing import TypedDict


class ErrorCode(IntEnum):
    SUCCESS = 200
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    NOT_FOUND = 404
    RATE_LIMIT = 429
    INTERNAL_ERROR = 500
    CUSTOM = 600


class CommandConfig(TypedDict):
    object_type: str
    prefix: str


EXPLICIT_COMMANDS: dict[str, CommandConfig] = {
    "/hs-contacts": {"object_type": "contacts", "prefix": "Searching contacts"},
    "/hs-leads": {"object_type": "leads", "prefix": "Searching leads"},
    "/hs-deals": {"object_type": "deals", "prefix": "Searching deals"},
    "/hs-companies": {"object_type": "companies", "prefix": "Searching companies"},
    "/hs-tickets": {"object_type": "tickets", "prefix": "Searching tickets"},
    "/hs-tasks": {"object_type": "tasks", "prefix": "Searching tasks"},
    "/hs-kb": {
        "object_type": "knowledge_article",
        "prefix": "Searching Knowledge Base",
    },
    "/hs-playbook": {
        "object_type": "knowledge_article",
        "prefix": "Searching Playbooks",
    },
}

CREATE_RECORD_CALLBACK_ID = "create_hubspot_record"
