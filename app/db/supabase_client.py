# app/db/supabase_client.py
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, TypeVar, cast

from anyio import to_thread
from supabase import Client, create_client

from app.core.config import settings
from app.core.logging import CorrelationAdapter, get_logger
from app.db.protocols import SupportsSingle

logger = get_logger("supabase")

T = TypeVar("T")


class SupabaseClient:
    """Async-friendly wrapper around the synchronous Supabase Python client.

    Features:
    - Executes all Supabase operations in a threadpool (non-blocking)
    - Supports select/order/limit
    - Real upsert (on_conflict)
    - Correlation-ID aware logging
    """

    def __init__(self, *, corr_id: str | None = None) -> None:
        self.client: Client = create_client(
            settings.SUPABASE_URL.unicode_string(),
            settings.SUPABASE_KEY.get_secret_value(),
        )
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
        self.log.info("Fetching single row from %s filters=%s", table, filters)

        query = self.client.table(table).select(
            ",".join(select) if select else "*"
        )

        for key, value in filters.items():
            query = query.eq(key, value)

        try:
            resp = await self._run(lambda: query.single().execute())
        except Exception as e:
            # Supabase errors include the full REST URL in the exception args
            self.log.error("SUPABASE ERROR: %s", e)

            # Some versions include the request URL in e.args[0]
            if e.args:
                self.log.error("SUPABASE RAW ERROR PAYLOAD: %s", e.args[0])

            raise


        raw = resp.data
        self.log.info("RAW SUPABASE ROW: %s", raw)
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
        self.log.info("Fetching many rows from %s filters=%s", table, filters)

        query = self.client.table(table).select(
            ",".join(select) if select else "*"
        )

        for key, value in filters.items():
            query = query.eq(key, value)

        if order_by:
            col, direction = order_by
            query = query.order(col, desc=(direction.lower() == "desc"))

        if limit:
            query = query.limit(limit)

        resp = await self._run(lambda: query.execute())
        return cast(Sequence[dict[str, Any]], resp.data or [])

    async def insert(
        self,
        table: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        self.log.info("Inserting into %s payload=%s", table, payload)

        builder = self.client.table(table).insert(payload)
        single_builder = cast(SupportsSingle, builder)

        resp = await self._run(lambda: single_builder.single().execute())
        return resp.data

    async def upsert(
        self,
        table: str,
        payload: Mapping[str, Any],
        *,
        on_conflict: str = "id",
    ) -> dict[str, Any] | None:
        self.log.info("Upserting into %s payload=%s", table, payload)

        builder = (
            self.client.table(table)
            .upsert(payload, on_conflict=on_conflict)
        )
        single_builder = cast(SupportsSingle, builder)

        resp = await self._run(lambda: single_builder.single().execute())
        return resp.data if isinstance(resp.data, dict) else None

    async def update(
        self,
        table: str,
        filters: Mapping[str, Any],
        payload: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        self.log.info("Updating %s filters=%s payload=%s", table, filters, payload)

        update_query = self.client.table(table).update(payload)
        for key, value in filters.items():
            update_query = update_query.eq(key, value)

        await self._run(lambda: update_query.execute())

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

        resp = await self._run(lambda: query.execute())
        return len(resp.data or [])

    async def count(
        self,
        table: str,
        filters: Mapping[str, Any],
    ) -> int:
        """Return count of rows matching filters (compatible with all Supabase versions)."""
        self.log.info("Counting rows in %s filters=%s", table, filters)

        query = self.client.table(table).select("id")

        for key, value in filters.items():
            query = query.eq(key, value)

        resp = await self._run(lambda: query.execute())

        data = resp.data or []
        return len(data)
