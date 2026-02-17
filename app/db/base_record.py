# app/db/base_record.py
from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from pydantic import BaseModel, ConfigDict, field_validator

from app.db.protocols import SupabaseRow
from app.utils.parsers import validate_supabase_row


class BaseRecord(BaseModel):
    """Base class for Supabase-backed records.

    Features:
    - Ignores extra fields from Supabase
    - Validates required fields
    - Provides safe constructors for optional rows
    - Supports conversion back to Supabase payloads
    - Immutable by default (safer for domain models)
    - Optional helpers for timestamps, updates, and PK access
    """

    model_config = ConfigDict(
        extra="ignore",
        frozen=True,
        populate_by_name=True,
    )

    # Override in subclasses
    required_fields: ClassVar[set[str]] = set()

    # ---------------------------------------------------------
    # Optional timestamp normalization
    # ---------------------------------------------------------
    @field_validator("created_at", "updated_at", mode="before", check_fields=False)
    def parse_timestamps(cls, v):
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        return v

    # ---------------------------------------------------------
    # Validation
    # ---------------------------------------------------------
    @classmethod
    def validate_required_fields(cls, data: SupabaseRow) -> None:
        if cls.required_fields:
            validate_supabase_row(data, list(cls.required_fields))

    # ---------------------------------------------------------
    # Constructors
    # ---------------------------------------------------------
    @classmethod
    def from_supabase(cls, data: SupabaseRow) -> Self:
        cls.validate_required_fields(data)
        return cls(**data)

    @classmethod
    def from_optional_supabase(cls, data: SupabaseRow | None) -> Self | None:
        if data is None:
            return None
        return cls.from_supabase(data)

    # ---------------------------------------------------------
    # Serialization
    # ---------------------------------------------------------
    def to_supabase(self) -> dict:
        """Convert record back to a Supabase-friendly dict."""
        return self.model_dump()

    def dict_for_update(self, exclude: set[str] | None = None) -> dict:
        """Return a dict suitable for update operations."""
        exclude = exclude or {"id", "created_at"}
        return self.model_dump(exclude=exclude)

    # ---------------------------------------------------------
    # Convenience helpers
    # ---------------------------------------------------------
    def pk(self) -> str:
        """Return the primary key (default: id)."""
        return getattr(self, "id")

    def copy_with(self, **updates) -> Self:
        """Immutable update helper."""
        return self.model_copy(update=updates)

    # ---------------------------------------------------------
    # Debugging
    # ---------------------------------------------------------
    def __repr__(self) -> str:
        fields = ", ".join(f"{k}={v!r}" for k, v in self.model_dump().items())
        return f"{self.__class__.__name__}({fields})"