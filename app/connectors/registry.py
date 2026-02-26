from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Protocol

from fastapi import APIRouter

from app.core.models.ui import UnifiedCard


class Renderer(Protocol):
    def render(self, card: UnifiedCard) -> dict[str, Any]: ...


@dataclass
class ConnectorManifest:
    name: str
    renderer: type[Renderer] | None = None
    service: type[Any] | None = None
    channel_service: type[Any] | None = None
    routers: list[APIRouter] = field(default_factory=list)


class ConnectorRegistry:
    """Central registry for multi-platform connectors (Slack, HubSpot, WhatsApp).

    Allows for dynamic discovery and registration of platform-specific components.
    """

    _connectors: ClassVar[dict[str, ConnectorManifest]] = {}

    @classmethod
    def register(
        cls,
        name: str,
        renderer: type[Renderer] | None = None,
        service: type[Any] | None = None,
        channel_service: type[Any] | None = None,
        routers: list[APIRouter] | None = None,
    ):
        cls._connectors[name] = ConnectorManifest(
            name=name,
            renderer=renderer,
            service=service,
            channel_service=channel_service,
            routers=routers or [],
        )

    @classmethod
    def get_connector(cls, name: str) -> ConnectorManifest | None:
        return cls._connectors.get(name)

    @classmethod
    def get_all_routers(cls) -> list[APIRouter]:
        routers = []
        for manifest in cls._connectors.values():
            routers.extend(manifest.routers)
        return routers


# Global instance
registry = ConnectorRegistry()
