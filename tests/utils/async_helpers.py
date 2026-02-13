# tests/utils/async_helpers.py
import asyncio

import pytest


def run(coro):
    """Run an async coroutine inside pytest."""
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture
def async_run():
    """Fixture wrapper for async execution."""
    return run
