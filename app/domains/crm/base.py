from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any


class BaseCRMService(ABC):
    """Abstract base class for all CRM domain services.
    Ensures a consistent interface for object lookup, search, and creation.
    """

    @abstractmethod
    async def get_object(
        self,
        *,
        workspace_id: str,
        object_type: str,
        object_id: str,
    ) -> Mapping[str, Any] | None:
        """Fetch a specific CRM object by its ID."""
        pass

    @abstractmethod
    async def search(
        self,
        *,
        workspace_id: str,
        object_type: str,
        query: str,
    ) -> list[dict[str, Any]]:
        """Search for CRM objects based on a query string."""
        pass

    @abstractmethod
    async def create_contact(
        self,
        workspace_id: str,
        properties: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Create a new contact in the CRM."""
        pass

    @abstractmethod
    async def create_task(
        self,
        workspace_id: str,
        properties: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Create a new task in the CRM."""
        pass

    @abstractmethod
    async def create_note(
        self,
        *,
        workspace_id: str,
        content: str,
        associated_id: str,
        associated_type: str,
    ) -> dict[str, Any]:
        """Create a note/activity associated with a CRM object."""
        pass
