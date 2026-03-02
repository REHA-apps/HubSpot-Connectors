from fastapi import APIRouter

from app.api.public.contact_router import router as contact_router
from app.api.public.privacy_router import router as privacy_router
from app.api.public.terms_router import router as terms_router
from app.connectors import setup_connectors
from app.connectors.registry import registry

# Initialize connectors
setup_connectors()

api_router = APIRouter()


@api_router.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


# Public pages
api_router.include_router(privacy_router)
api_router.include_router(terms_router)
api_router.include_router(contact_router)

# Dynamic Connector Routers
for connector_router in registry.get_all_routers():
    api_router.include_router(connector_router)
