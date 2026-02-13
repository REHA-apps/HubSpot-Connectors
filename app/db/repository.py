# app/db/repository.py
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Generic, TypeVar

from app.db.protocols import SupabaseModel
from app.db.supabase_client import SupabaseClient

R = TypeVar("R", bound=SupabaseModel)


class SupabaseRepository(Generic[R]):
    """Generic repository for a single Supabase table + record type."""

    def __init__(self, client: SupabaseClient, table: str, model: type[R]) -> None:
        self.client = client
        self.table = table
        self.model = model

    def fetch_single(self, filters: Mapping[str, Any]) -> R | None:
        return self.client.fetch_single(self.table, filters, self.model)

    def upsert(self, payload: Mapping[str, Any]) -> None:
        self.client.upsert(self.table, payload)

    def update(self, filters: Mapping[str, Any], payload: Mapping[str, Any]) -> None:
        self.client.update(self.table, filters, payload)

    def delete(self, filters: Mapping[str, Any]) -> None:
        self.client.delete(self.table, filters)
