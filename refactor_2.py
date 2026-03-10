import re

files = [
    "app/connectors/hubspot_slack/services/handlers/action_handlers.py",
    "app/connectors/hubspot_slack/services/handlers/modal_handlers.py",
    "app/connectors/hubspot_slack/services/handlers/object_handlers.py",
    "app/connectors/hubspot_slack/services/handlers/base.py",
    "app/connectors/hubspot_slack/services/service.py",
    "app/connectors/hubspot_slack/services/command_service.py",
]

for filepath in files:
    with open(filepath, encoding="utf-8") as f:
        content = f.read()

    # Add IntegrationRecord to imports if not there
    if (
        "integration: Any" in content
        and "IntegrationRecord" not in content
        and filepath != "app/connectors/hubspot_slack/services/handlers/base.py"
    ):
        if "from typing import Any" in content:
            content = content.replace(
                "from typing import Any",
                "from typing import Any\nfrom app.db.records import IntegrationRecord",
            )
        else:
            content = "from app.db.records import IntegrationRecord\n" + content

    content = content.replace("integration: Any", "integration: IntegrationRecord")

    # regex to find logger.error(..., exc) -> logger.exception(...)
    # e.g. logger.error("Failed to map: %s", exc) -> logger.exception("Failed to map")
    content = re.sub(
        r'logger\.error\("([^"]+)(?:: %s)?",\s+exc(?:,\s*exc_info=True)?\)',
        r'logger.exception("\1")',
        content,
    )

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
print("Finished second refactoring")
