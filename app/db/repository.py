from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Generic, TypeVar

from app.core.logging import CorrelationAdapter, get_logger
from app.db.protocols import SupabaseModel, SupabaseRow
from app.db.supabase_client import SupabaseClient

R = TypeVar("R", bound=SupabaseModel)

logger = get_logger("supabase.repo")


class SupabaseRepository(Generic[R]):
    """Generic async repository for a single Supabase table + record type.

    Improvements:
    - Repo logs downgraded to DEBUG (client logs remain INFO)
    - Cleaner, more predictable API
    - No duplicate logging noise
    """

    def __init__(
        self,
        client: SupabaseClient,
        table: str,
        model: type[R],
        corr_id: str,
    ) -> None:
        self.client = client
        self.table = table
        self.model = model
        self.log = CorrelationAdapter(logger, corr_id)

    # ---------------------------------------------------------
    # Fetching
    # ---------------------------------------------------------
    async def fetch_single(self, filters: Mapping[str, Any]) -> R | None:
        self.log.debug("fetch_single(%s, filters=%s)", self.table, filters)

        row = await self.client.fetch_single(self.table, filters)
        if row is None:
            return None

        return self.model.from_supabase(row)

    async def fetch_many(self, filters: Mapping[str, Any]) -> list[R]:
        self.log.debug("fetch_many(%s, filters=%s)", self.table, filters)

        rows: Sequence[SupabaseRow] = await self.client.fetch_many(self.table, filters)
        return [self.model.from_supabase(r) for r in rows]

    # ---------------------------------------------------------
    # Insert / Upsert / Update
    # ---------------------------------------------------------
    async def insert(self, payload: Mapping[str, Any]) -> R:
        self.log.debug("insert(%s): %s", self.table, payload)

        row = await self.client.insert(self.table, payload)
        return self.model.from_supabase(row)

    async def upsert(self, payload: Mapping[str, Any]) -> R:
        self.log.debug("upsert(%s): %s", self.table, payload)

        row = await self.client.upsert(self.table, payload)
        if row is None:
            raise RuntimeError(
                f"Supabase upsert returned None for table={self.table}, "
                f"payload={payload}"
            )
        return self.model.from_supabase(row)

    async def update(
        self,
        filters: Mapping[str, Any],
        payload: Mapping[str, Any],
    ) -> R | None:
        self.log.debug(
            "update(%s, filters=%s, payload=%s)",
            self.table,
            filters,
            payload,
        )

        row = await self.client.update(self.table, filters, payload)
        if row is None:
            return None

        return self.model.from_supabase(row)

    # ---------------------------------------------------------
    # Delete
    # ---------------------------------------------------------
    async def delete(self, filters: Mapping[str, Any]) -> int:
        self.log.debug("delete(%s, filters=%s)", self.table, filters)

        return await self.client.delete(self.table, filters)

    # ---------------------------------------------------------
    # Utility
    # ---------------------------------------------------------
    async def exists(self, filters: Mapping[str, Any]) -> bool:
        return (await self.fetch_single(filters)) is not None
