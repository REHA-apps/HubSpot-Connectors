from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Generic, TypeVar

from app.core.logging import CorrelationAdapter, get_logger
from app.db.protocols import SupabaseModel, SupabaseRow
from app.db.supabase_client import SupabaseClient

R = TypeVar("R", bound=SupabaseModel)

logger = get_logger("supabase.repo")


class SupabaseRepository(Generic[R]):  # noqa: UP046
    """Description:
        Generic asynchronous repository for typed CRUD operations on Supabase tables.

    Rules Applied:
        - Enforces strong typing via Pydantic model integration.
        - Provides standard hooks for fetching single or multiple records with filters.
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

    # Fetching operations
    async def fetch_single(
        self,
        filters: Mapping[str, Any],
        *,
        select: Sequence[str] | None = None,
    ) -> R | None:
        self.log.debug("fetch_single(%s, filters=%s)", self.table, filters)

        row = await self.client.fetch_single(self.table, filters, select=select)
        if row is None:
            return None

        return self.model.from_supabase(row)

    async def fetch_many(
        self,
        filters: Mapping[str, Any],
        *,
        select: Sequence[str] | None = None,
        order_by: tuple[str, str] | None = None,  # ("created_at", "desc")
        limit: int | None = None,
    ) -> list[R]:
        self.log.debug("fetch_many(%s, filters=%s)", self.table, filters)

        rows: Sequence[SupabaseRow] = await self.client.fetch_many(
            self.table,
            filters,
            select=select,
            order_by=order_by,
            limit=limit,
        )
        return [self.model.from_supabase(r) for r in rows]

    # Mutation operations
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

    # Deletion operations
    async def delete(self, filters: Mapping[str, Any]) -> int:
        self.log.debug("delete(%s, filters=%s)", self.table, filters)
        return await self.client.delete(self.table, filters)

    # Utility operations
    async def exists(self, filters: Mapping[str, Any]) -> bool:
        """Optimized existence check using select('id')."""
        row = await self.client.fetch_single(self.table, filters, select=["id"])
        return row is not None

    async def first_or_none(
        self,
        filters: Mapping[str, Any],
        *,
        order_by: tuple[str, str] | None = None,
    ) -> R | None:
        rows = await self.fetch_many(filters, order_by=order_by, limit=1)
        return rows[0] if rows else None

    async def count(self, filters: Mapping[str, Any]) -> int:
        """Return the number of rows matching the given filters."""
        return await self.client.count(self.table, filters)
