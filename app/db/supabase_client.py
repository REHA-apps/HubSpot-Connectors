# app/db/supabase_client.py
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from supabase import Client, create_client

from app.core.config import settings
from app.core.logging import CorrelationAdapter, get_logger
from app.db.protocols import SupabaseModel, SupabaseRow

T = TypeVar("T", bound=SupabaseModel)

logger = get_logger("supabase")


class SupabaseClient:
    """Thin wrapper around the Supabase Python client with:
    - typed fetch_single
    - typed update/upsert/delete
    - correlation-ID logging
    - Python 3.12 typing
    - Pyright-clean signatures
    """

    def __init__(self, *, corr_id: str | None = None) -> None:
        self.client: Client = create_client(
            settings.SUPABASE_URL.unicode_string(),
            settings.SUPABASE_KEY.get_secret_value(),
        )
        self.log = CorrelationAdapter(logger, corr_id or "supabase")

    # ------------------------------------------------------------------
    # Fetch single row
    # ------------------------------------------------------------------
    def fetch_single(
        self,
        table: str,
        filters: Mapping[str, Any],
        model: type[T],
    ) -> T | None:
        self.log.info("Fetching single row from table=%s filters=%s", table, filters)

        query = self.client.table(table).select("*")
        for key, value in filters.items():
            query = query.eq(key, value)

        resp = query.single().execute()
        raw = resp.data

        if not isinstance(raw, dict):
            self.log.info("No row found for table=%s filters=%s", table, filters)
            return None

        row = cast(SupabaseRow, raw)
        return model.from_supabase(row)

    # ------------------------------------------------------------------
    # Upsert
    # ------------------------------------------------------------------
    def upsert(self, table: str, payload: Mapping[str, Any]) -> None:
        self.log.info("Upserting into table=%s payload=%s", table, payload)
        self.client.table(table).upsert(payload).execute()

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------
    def update(
        self,
        table: str,
        filters: Mapping[str, Any],
        payload: Mapping[str, Any],
    ) -> None:
        self.log.info(
            "Updating table=%s filters=%s payload=%s",
            table,
            filters,
            payload,
        )

        query = self.client.table(table).update(payload)
        for key, value in filters.items():
            query = query.eq(key, value)

        query.execute()

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------
    def delete(self, table: str, filters: Mapping[str, Any]) -> None:
        self.log.info("Deleting from table=%s filters=%s", table, filters)

        query = self.client.table(table).delete()
        for key, value in filters.items():
            query = query.eq(key, value)

        query.execute()
