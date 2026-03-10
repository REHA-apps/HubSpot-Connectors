from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, TypeVar

from app.core.logging import get_logger
from app.db.protocols import SupabaseModel, SupabaseRow
from app.db.supabase_client import SupabaseClient

R = TypeVar("R", bound=SupabaseModel)

logger = get_logger("supabase.repo")


class SupabaseRepository[R: SupabaseModel]:
    """Generic asynchronous repository for typed CRUD operations on Supabase tables.

    Attributes:
        client: The underlying database client.
        table: The name of the table this repository manages.
        model: The Pydantic model for record validation and conversion.

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

    # Fetching operations
    async def fetch_single(
        self,
        filters: Mapping[str, Any],
        *,
        select: Sequence[str] | None = None,
    ) -> R | None:
        """Fetches a single record and converts it to the model.

        Args:
            filters: Equivalence filters.
            select: Column selection override.

        Returns:
            The model instance or None if not found.

        """
        logger.debug("fetch_single(%s, filters=%s)", self.table, filters)

        row = await self.client.fetch_single(self.table, filters, select=select)
        if row is None:
            return None

        return self.model.from_supabase(row)

    async def fetch_many(
        self,
        filters: Mapping[str, Any],
        *,
        select: Sequence[str] | None = None,
        order_by: tuple[str, str] | None = None,
        limit: int | None = None,
    ) -> list[R]:
        """Fetches multiple records and converts them to models.

        Args:
            filters: Equivalence filters.
            select: Column selection override.
            order_by: Tuple of (column, direction).
            limit: Maximum number of rows.

        Returns:
            A list of model instances.

        """
        logger.debug("fetch_many(%s, filters=%s)", self.table, filters)

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
        """Inserts a record and returns the validated model.

        Args:
            payload: Row data.

        Returns:
            The created model instance.

        """
        logger.debug("insert(%s): %s", self.table, payload)

        row = await self.client.insert(self.table, payload)
        return self.model.from_supabase(row)

    async def upsert(self, payload: Mapping[str, Any]) -> R:
        """Upserts a record and returns the validated model.

        Args:
            payload: Row data.

        Returns:
            The upserted model instance.

        Raises:
            RuntimeError: If upsert returns no data.

        """
        logger.debug("upsert(%s): %s", self.table, payload)

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
        """Updates records and returns the first updated model.

        Args:
            filters: Filters identifying the row.
            payload: New values.

        Returns:
            The updated model or None if not found.

        """
        logger.debug(
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
        logger.debug("delete(%s, filters=%s)", self.table, filters)
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
