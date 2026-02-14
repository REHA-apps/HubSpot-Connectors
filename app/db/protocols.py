from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any, Protocol, Self, TypedDict

# ---------------------------------------------------------
# JSON Types
# ---------------------------------------------------------
type JSONValue = str | int | float | bool | None | dict[str, Any] | list[Any]
type JSONDict = dict[str, JSONValue]
type SupabaseList = list[JSONDict]


# ---------------------------------------------------------
# Supabase Row Protocol
# ---------------------------------------------------------
class SupabaseRow(Protocol):
    """A minimal protocol describing a row returned by Supabase.

    Supabase returns dict-like objects, so we only require:
    - __getitem__
    - keys()
    - Mapping behavior
    """

    def __getitem__(self, key: str, /) -> Any: ...
    def keys(self) -> Iterable[str]: ...
    def __iter__(self) -> Iterator[str]: ...
    def __len__(self) -> int: ...


# ---------------------------------------------------------
# TypedDict for stricter static typing (optional)
# ---------------------------------------------------------
class SupabaseRowDict(TypedDict, total=False):
    """A TypedDict version of a Supabase row.
    Useful for autocomplete and static analysis.
    """

    id: Any
    created_at: Any
    updated_at: Any
    # Subclasses can extend this


# ---------------------------------------------------------
# Supabase Model Protocol
# ---------------------------------------------------------
class SupabaseModel(Protocol):
    """Protocol for models that can be constructed from a Supabase row."""

    @classmethod
    def from_supabase(cls, data: SupabaseRow) -> Self: ...


class SupportsSingle(Protocol):
    def single(self) -> Any: ...
