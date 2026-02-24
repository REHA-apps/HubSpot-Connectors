import asyncio
from datetime import UTC, datetime, timedelta

from app.core.logging import get_logger
from app.db.records import PlanTier
from app.db.storage_service import StorageService

logger = get_logger("scripts.update_tier")


async def update_expired_trials():
    """Finds all workspaces with expired trials and no active subscription,
    and downgrades them to the FREE tier.
    """
    storage = StorageService(corr_id="cron-tier-update")
    workspaces = await storage.list_all_workspaces()

    now = datetime.now(UTC)
    downgrade_count = 0

    for workspace in workspaces:
        # Skip if already PRO by explicit tier or active subscription
        if workspace.tier == PlanTier.PRO or workspace.subscription_status == "active":
            continue

        install_date = workspace.install_date or workspace.created_at
        if not install_date:
            continue

        if install_date.tzinfo is None:
            install_date = install_date.replace(tzinfo=UTC)

        if now > install_date + timedelta(days=14):
            logger.info(
                "Downgrading workspace %s to FREE tier (trial expired)", workspace.id
            )
            await storage.upsert_workspace(
                workspace_id=workspace.id,
            )
            # Note: upsert_workspace defaults to FREE and inactive status if not
            # provided, but we should be explicit if we want to ensure it.
            # Actually, our upsert_workspace only updates fields provided.
            # We need a way to explicitly set tier=FREE.

            # Let's use the underlying collection for explicit update
            await storage.workspaces.upsert(
                {
                    "id": workspace.id,
                    "tier": PlanTier.FREE,
                    "subscription_status": "inactive",
                }
            )
            downgrade_count += 1

    logger.info("Maintenance complete. Downgraded %d workspaces.", downgrade_count)


if __name__ == "__main__":
    asyncio.run(update_expired_trials())
