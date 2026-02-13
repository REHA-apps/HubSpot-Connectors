# app/db/protocols.py
from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol, Self, TypeAlias

JSON: TypeAlias = str | int | float | bool | None | dict[str, Any] | list[Any]
JSONDict: TypeAlias = dict[str, JSON]


class SupabaseRow(Protocol):
    """A minimal protocol describing a row returned by Supabase.
    Supabase returns dict-like objects, so we only require the parts we use.
    """

    def __getitem__(self, key: str) -> Any: ...
    def keys(self) -> Iterable[str]: ...


class SupabaseModel(Protocol):
    """Protocol for models that can be constructed from a Supabase row."""

    @classmethod
    def from_supabase(cls, data: SupabaseRow) -> Self: ...
