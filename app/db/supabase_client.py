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

    Key features:
    - Executes all Supabase operations in a threadpool (non-blocking)
    - Typed fetch_single / fetch_many
    - Typed insert / update / upsert
    - Correlation-ID aware logging
    """

    def __init__(self, *, corr_id: str | None = None) -> None:
        self.client: Client = create_client(
            settings.SUPABASE_URL.unicode_string(),
            settings.SUPABASE_KEY.get_secret_value(),
        )
        self.log = CorrelationAdapter(logger, corr_id or "supabase")

    @property
    def postgrest(self):
        return self.client.postgrest

    # ---------------------------------------------------------
    # Internal helper: run sync Supabase calls in threadpool
    # ---------------------------------------------------------
    async def _run(self, fn: Callable[[], T]) -> T:
        return await to_thread.run_sync(fn)

    # ---------------------------------------------------------
    # Fetch single
    # ---------------------------------------------------------
    async def fetch_single(
        self,
        table: str,
        filters: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        self.log.info("Fetching single row from %s filters=%s", table, filters)

        query = self.client.table(table).select("*")
        for key, value in filters.items():
            query = query.eq(key, value)

        resp = await self._run(lambda: query.single().execute())
        raw = resp.data

        if not isinstance(raw, dict):
            self.log.info("No row found for %s filters=%s", table, filters)
            return None

        return raw

    # ---------------------------------------------------------
    # Fetch many
    # ---------------------------------------------------------
    async def fetch_many(
        self,
        table: str,
        filters: Mapping[str, Any],
    ) -> Sequence[dict[str, Any]]:
        self.log.info("Fetching many rows from %s filters=%s", table, filters)

        query = self.client.table(table).select("*")
        for key, value in filters.items():
            query = query.eq(key, value)

        resp = await self._run(lambda: query.execute())
        data = resp.data or []

        # Runtime guarantee: Supabase returns list[dict[str, Any]]
        return cast(Sequence[dict[str, Any]], data)

    # ---------------------------------------------------------
    # Insert
    # ---------------------------------------------------------
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

    # ---------------------------------------------------------
    # Upsert
    # ---------------------------------------------------------
    async def upsert(
        self,
        table: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        self.log.info("Upserting into %s payload=%s", table, payload)

        resp = await self._run(
            lambda: cast(SupportsSingle, self.client.table(table).insert(payload))
            .single()
            .execute()
        )
        return resp.data if isinstance(resp.data, dict) else None

    # ---------------------------------------------------------
    # Update
    # ---------------------------------------------------------
    async def update(self, table, filters, payload):
        # 1. Update
        update_query = self.client.table(table).update(payload)
        for key, value in filters.items():
            update_query = update_query.eq(key, value)

        await self._run(lambda: update_query.execute())

        # 2. Fetch updated row
        select_query = self.client.table(table).select("*")
        for key, value in filters.items():
            select_query = select_query.eq(key, value)

        resp = await self._run(lambda: select_query.single().execute())
        return resp.data if isinstance(resp.data, dict) else None

    # ------------------------------    ---------------------------
    # Delete
    # ---------------------------------------------------------
    async def delete(
        self,
        table: str,
        filters: Mapping[str, Any],
    ) -> int:
        self.log.info("Deleting from %s filters=%s", table, filters)

        query = self.client.table(table).delete()
        for key, value in filters.items():
            query = query.eq(key, value)

        resp = await self._run(lambda: cast(SupportsSingle, query).single().execute())
        return len(resp.data or [])
