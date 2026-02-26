from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from pydantic import BaseModel, ConfigDict, field_validator

from app.db.protocols import SupabaseRow
from app.utils.parsers import validate_supabase_row


class BaseRecord(BaseModel):
    """Description:
        Base Pydantic model for all Supabase database records.

    Rules Applied:
        - Enforces immutability (frozen=True) for domain data integrity.
        - Provides standardized constructors and serialization helpers (Supabase).
        - Automatically handles timestamp normalization.
    """

    model_config = ConfigDict(
        extra="ignore",
        frozen=True,
        populate_by_name=True,
    )

    # Override in subclasses
    required_fields: ClassVar[set[str]] = set()

    # Timestamp normalization
    @field_validator("created_at", "updated_at", mode="before", check_fields=False)
    def parse_timestamps(cls, v: str | datetime | None) -> datetime | None:
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        return v

    # Validation helpers
    @classmethod
    def validate_required_fields(cls, data: SupabaseRow) -> None:
        if cls.required_fields:
            validate_supabase_row(data, list(cls.required_fields))

    # Record constructors
    @classmethod
    def from_supabase(cls, data: SupabaseRow) -> Self:
        cls.validate_required_fields(data)
        return cls(**data)

    @classmethod
    def from_optional_supabase(cls, data: SupabaseRow | None) -> Self | None:
        if data is None:
            return None
        return cls.from_supabase(data)

    # Serialization helpers
    def to_supabase(self) -> dict:
        """Convert record back to a Supabase-friendly dict."""
        return self.model_dump()

    def dict_for_update(self, exclude: set[str] | None = None) -> dict:
        """Return a dict suitable for update operations."""
        exclude = exclude or {"id", "created_at"}
        return self.model_dump(exclude=exclude)

    # Utility helpers
    def pk(self) -> str:
        """Return the primary key (default: id)."""
        return getattr(self, "id")

    def copy_with(self, **updates) -> Self:
        """Immutable update helper."""
        return self.model_copy(update=updates)

    # Debug helpers
    def __repr__(self) -> str:
        fields = ", ".join(f"{k}={v!r}" for k, v in self.model_dump().items())
        return f"{self.__class__.__name__}({fields})"
