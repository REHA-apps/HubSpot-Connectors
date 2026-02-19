# app/core/dependencies.py
"""Per-request dependency factories for FastAPI's Depends() system.

FastAPI caches Depends() results per-request, so calling get_storage_service
from multiple services in the same handler returns the SAME instance.
"""

from __future__ import annotations

from fastapi import Depends

from app.core.logging import get_corr_id
from app.db.storage_service import StorageService
from app.domains.ai.service import AIService
from app.domains.crm.hubspot.service import HubSpotService
from app.domains.crm.integration_service import IntegrationService
from app.domains.crm.service import CRMService


def get_storage_service(
    corr_id: str = Depends(get_corr_id),
) -> StorageService:
    """One StorageService per request."""
    return StorageService(corr_id)


def get_ai_service(
    corr_id: str = Depends(get_corr_id),
) -> AIService:
    """One AIService per request."""
    return AIService(corr_id)


def get_integration_service(
    corr_id: str = Depends(get_corr_id),
    storage: StorageService = Depends(get_storage_service),
) -> IntegrationService:
    """One IntegrationService per request, sharing StorageService."""
    return IntegrationService(corr_id, storage=storage)


def get_crm_service(
    corr_id: str = Depends(get_corr_id),
) -> CRMService:
    """One CRMService per request."""
    return CRMService(corr_id)


def get_hubspot_service(
    corr_id: str = Depends(get_corr_id),
) -> HubSpotService:
    """One HubSpotService per request (delegated to CRMService)."""
    return CRMService(corr_id).hubspot
