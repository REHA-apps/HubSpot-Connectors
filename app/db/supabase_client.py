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
        return await to_thread.run_sync(fn)

    async def fetch_single(
        self,
        table: str,
        filters: Mapping[str, Any],
        *,
        select: Sequence[str] | None = None,
    ) -> dict[str, Any] | None:
        """Description:
            Fetches a single record from the database matching the provided criteria.

        Args:
            table (str): Target table name.
            filters (Mapping[str, Any]): Equivalence filters (column: value).
            select (Sequence[str] | None): Column selection override.

        Returns:
            dict[str, Any] | None: The record payload or None if not found.

        """
        self.log.debug("Fetching single row from %s filters=%s", table, filters)

        query = self.client.table(table).select(",".join(select) if select else "*")

        for key, value in filters.items():
            query = query.eq(key, value)

        try:
            resp = await self._run(query.single().execute)
        except Exception as e:
            # Handle "0 rows" error from .single()
            if hasattr(e, "code") and getattr(e, "code") == "PGRST116":
                self.log.info("No row found in %s for filters=%s", table, filters)
                return None

            # For some versions, the error might be in the args or as a string
            err_msg = str(e)
            if "PGRST116" in err_msg or "0 rows" in err_msg:
                self.log.info(
                    "No row found in %s for filters=%s (caught via msg)", table, filters
                )
                return None

            self.log.error("SUPABASE ERROR: %s", e)
            if e.args:
                self.log.error("SUPABASE RAW ERROR PAYLOAD: %s", e.args[0])
            raise

        raw = resp.data
        self.log.debug(
            "Supabase fetch_single from %s: row_found=%s", table, raw is not None
        )
        if not isinstance(raw, dict):
            self.log.info("No row found for %s filters=%s", table, filters)
            return None

        return raw

    async def fetch_many(
        self,
        table: str,
        filters: Mapping[str, Any],
        *,
        select: Sequence[str] | None = None,
        order_by: tuple[str, str] | None = None,
        limit: int | None = None,
    ) -> Sequence[dict[str, Any]]:
        self.log.debug("Fetching many rows from %s filters=%s", table, filters)

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
        self.log.debug("Inserting into %s", table)

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
    ) -> dict[str, Any] | None:
        self.log.debug("Upserting into %s", table)

        serialized_payload = _serialize_payload(dict(payload))
        query = self.client.table(table).upsert(
            serialized_payload, on_conflict=on_conflict
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
        self.log.debug("Updating %s filters=%s", table, filters)

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
        self.log.info("Deleting from %s filters=%s", table, filters)

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
        """Return count of rows matching filters (Supabase version compatible)."""
        self.log.info("Counting rows in %s filters=%s", table, filters)

        query = self.client.table(table).select("id")

        for key, value in filters.items():
            query = query.eq(key, value)

        resp = await self._run(query.execute)

        data = resp.data or []
        return len(data)
