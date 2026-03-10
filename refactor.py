import re

files = [
    "app/connectors/hubspot_slack/services/handlers/action_handlers.py",
    "app/connectors/hubspot_slack/services/handlers/modal_handlers.py",
    "app/connectors/hubspot_slack/services/handlers/object_handlers.py",
]

sig_regex = re.compile(
    r"(\s+messaging_service:\s*SlackMessagingService,)(.*?)(?=\s+\)\s*->)", re.DOTALL
)

for filepath in files:
    with open(filepath, encoding="utf-8") as f:
        content = f.read()

    # Add InteractionContext to imports
    if "from .base import " in content and "InteractionContext" not in content:
        content = content.replace(
            "from .base import ", "from .base import InteractionContext, "
        )

    # Add context: InteractionContext to signatures
    content = sig_regex.sub(r"\1\n        context: InteractionContext,\2", content)

    # Replacements for context variables
    content = re.sub(
        r'payload\.get\("user",\s*\{\}\)\.get\("id"\)(?:\s*or\s*"")?',
        r"context.user_id",
        content,
    )
    content = re.sub(
        r'payload\.get\("user",\s*\{\}\)\.get\("id",\s*""\)',
        r"context.user_id",
        content,
    )
    content = re.sub(
        r'payload\.get\("user"\)\.get\("id"\)', r"context.user_id", content
    )

    content = re.sub(
        r'payload\.get\("channel",\s*\{\}\)\.get\("id"\)(?:\s*or\s*"")?',
        r"context.channel_id",
        content,
    )
    content = re.sub(
        r'payload\.get\("channel",\s*\{\}\)\.get\("id",\s*""\)',
        r"context.channel_id",
        content,
    )

    content = re.sub(r"str\(context\.user_id\)", r"context.user_id", content)
    content = re.sub(r"str\(context\.channel_id\)", r"str(context.channel_id)", content)

    content = re.sub(r'kwargs\.get\("channel_id"\)', r"context.channel_id", content)
    content = re.sub(r'kwargs\.get\("response_url"\)', r"context.response_url", content)
    content = re.sub(
        r'payload\.get\("response_url"\)', r"context.response_url", content
    )

    content = re.sub(r'kwargs\.get\("trigger_id"\)', r"context.trigger_id", content)
    content = re.sub(r'payload\.get\("trigger_id"\)', r"context.trigger_id", content)

    content = re.sub(r'kwargs\.get\("value",\s*""\)', r'context.value or ""', content)
    content = re.sub(r'kwargs\.get\("value"\)', r"context.value", content)

    content = re.sub(r'kwargs\.get\("action_id"\)', r"context.action_id", content)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
print("Finished refactoring")
