from __future__ import annotations

import datetime
from collections.abc import Callable, Mapping, Sequence
from typing import Any, TypeVar, cast

from anyio import to_thread
from supabase import Client, create_client

from app.core.config import settings
from app.core.logging import CorrelationAdapter, get_logger

logger = get_logger("supabase")

T = TypeVar("T")

# Module-level Supabase connection singleton.
# Avoids creating a new connection per request (~100-300ms savings).
_supabase_singleton: Client | None = None


def _get_supabase_client() -> Client:
    """Return the shared Supabase Client, creating it on first use."""
    global _supabase_singleton  # noqa: PLW0603
    if _supabase_singleton is None:
        _supabase_singleton = create_client(
            settings.SUPABASE_URL.unicode_string(),
            settings.SUPABASE_KEY.get_secret_value(),
        )
    return _supabase_singleton


def _serialize_payload(obj: Any) -> Any:
    """Recursively serialize datetime objects for Supabase JSON columns."""
    if isinstance(obj, dict):
        return {k: _serialize_payload(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize_payload(item) for item in obj]
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    if isinstance(obj, datetime.date):
        return obj.isoformat()
    return obj


class SupabaseClient:
    """Asynchronous-aware wrapper for the synchronous Supabase Python SDK.

    Uses a module-level singleton for the underlying Supabase connection
    to avoid re-creating it on every request.
    """

    def __init__(self, *, corr_id: str | None = None) -> None:
        self.client: Client = _get_supabase_client()
        self.log = CorrelationAdapter(logger, corr_id or "supabase")

    async def _run(self, fn: Callable[[], T]) -> T:
        """Executes a synchronous Supabase operation in a separate thread.

        Args:
            fn: The blocking function to execute.

        Returns:
            The result of the operation.

        """
        return await to_thread.run_sync(fn)

    async def fetch_single(
        self,
        table: str,
        filters: Mapping[str, Any],
        *,
        select: Sequence[str] | None = None,
    ) -> dict[str, Any] | None:
        """Fetches a single record matching the filters.

        Args:
            table: Target table name.
            filters: Equivalence filters (column: value).
            select: Column selection override.

        Returns:
            The record payload or None if not found.

        """
        logger.debug("Fetching single row from %s filters=%s", table, filters)

        query = self.client.table(table).select(",".join(select) if select else "*")

        for key, value in filters.items():
            query = query.eq(key, value)

        # Use limit(1) instead of single() to handle unintentional duplicates gracefully
        query = query.limit(1)

        resp = await self._run(query.execute)
        data = resp.data

        if not data or not isinstance(data, list) or len(data) == 0:
            logger.debug("No row found in %s filters=%s", table, filters)
            return None

        return cast(dict[str, Any], data[0])

    async def fetch_many(
        self,
        table: str,
        filters: Mapping[str, Any],
        *,
        select: Sequence[str] | None = None,
        order_by: tuple[str, str] | None = None,
        limit: int | None = None,
    ) -> Sequence[dict[str, Any]]:
        """Fetches multiple records from the database.

        Args:
            table: Target table name.
            filters: Equivalence filters (column: value).
            select: Column selection override.
            order_by: Tuple of (column, direction).
            limit: Maximum number of rows.

        Returns:
            A sequence of record payloads.

        """
        logger.debug("Fetching many rows from %s filters=%s", table, filters)

        query = self.client.table(table).select(",".join(select) if select else "*")

        for key, value in filters.items():
            query = query.eq(key, value)

        if order_by:
            col, direction = order_by
            query = query.order(col, desc=(direction.lower() == "desc"))

        if limit:
            query = query.limit(limit)

        resp = await self._run(query.execute)
        return cast(Sequence[dict[str, Any]], resp.data or [])

    async def insert(
        self,
        table: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Inserts a new record into the database.

        Args:
            table: Target table name.
            payload: Row data to insert.

        Returns:
            The inserted record payload.

        """
        logger.debug("Inserting into %s", table)

        serialized_payload = _serialize_payload(dict(payload))
        query = self.client.table(table).insert(serialized_payload)
        resp = await self._run(query.execute)

        # In newer versions, data might be a list or a dict
        data = resp.data
        if isinstance(data, list) and len(data) > 0:
            val = data[0]
            if isinstance(val, dict):
                return cast(dict[str, Any], val)
            return cast(dict[str, Any], {"value": val})  # Should be rare
        return cast(dict[str, Any], data)

    async def upsert(
        self,
        table: str,
        payload: Mapping[str, Any],
        *,
        on_conflict: str = "id",
        ignore_duplicates: bool = False,
    ) -> dict[str, Any] | None:
        """Upserts a record into the database.

        Args:
            table: Target table name.
            payload: Row data to upsert.
            on_conflict: Conflict resolution column.
            ignore_duplicates: Whether to ignore duplicate keys.

        Returns:
            The upserted record payload or None on failure.

        """
        logger.debug("Upserting into %s", table)

        serialized_payload = _serialize_payload(dict(payload))
        query = self.client.table(table).upsert(
            serialized_payload,
            on_conflict=on_conflict,
            ignore_duplicates=ignore_duplicates,
        )
        resp = await self._run(query.execute)

        data = resp.data
        if isinstance(data, list) and len(data) > 0:
            val = data[0]
            if isinstance(val, dict):
                return cast(dict[str, Any], val)
            return None
        return cast(dict[str, Any], data) if isinstance(data, dict) else None

    async def update(
        self,
        table: str,
        filters: Mapping[str, Any],
        payload: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        """Updates records matching the filters.

        Args:
            table: Target table name.
            filters: Equivalence filters identifying the row(s).
            payload: New values to set.

        Returns:
            The updated record payload or None if not found.

        """
        logger.debug("Updating %s filters=%s", table, filters)

        serialized_payload = _serialize_payload(dict(payload))
        update_query = self.client.table(table).update(serialized_payload)
        for key, value in filters.items():
            update_query = update_query.eq(key, value)

        await self._run(update_query.execute)

        # Fetch updated row
        return await self.fetch_single(table, filters)

    async def delete(
        self,
        table: str,
        filters: Mapping[str, Any],
    ) -> int:
        """Deletes records matching the filters.

        Args:
            table: Target table name.
            filters: Equivalence filters identifying the row(s).

        Returns:
            The number of deleted records.

        """
        logger.info("Deleting from %s filters=%s", table, filters)

        query = self.client.table(table).delete()
        for key, value in filters.items():
            query = query.eq(key, value)

        resp = await self._run(query.execute)
        return len(resp.data or [])

    async def count(
        self,
        table: str,
        filters: Mapping[str, Any],
    ) -> int:
        """Return count of rows matching filters.

        Args:
            table: Target table name.
            filters: Equivalence filters identifying the rows.

        Returns:
            The count of matching records.

        """
        logger.info("Counting rows in %s filters=%s", table, filters)

        query = self.client.table(table).select("id")

        for key, value in filters.items():
            query = query.eq(key, value)

        resp = await self._run(query.execute)

        data = resp.data or []
        return len(data)
