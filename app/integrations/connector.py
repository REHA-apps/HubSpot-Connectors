from abc import ABC, abstractmethod
from typing import Dict, Any

class Connector(ABC):
    """Base class for all CRM and communication connectors."""

    @abstractmethod
    async def send_event(self, event: Dict[str, Any]):
        """Sends a notification or event to the target platform."""
        pass

    @abstractmethod
    async def handle_event(self, event: Dict[str, Any]):
        """Processes an incoming event from the target platform."""
        pass
