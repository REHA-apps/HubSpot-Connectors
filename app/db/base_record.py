# app/db/base_record.py
from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar, Self

from pydantic import BaseModel, ConfigDict

from app.db.protocols import SupabaseRow
from app.utils.parsers import validate_supabase_row


class BaseRecord(BaseModel):
    """Base class for Supabase-backed records.
    - Ignores extra fields from Supabase
    - Provides from_supabase with required-field validation
    """

    model_config = ConfigDict(extra="ignore")

    # Override in subclasses
    required_fields: ClassVar[Iterable[str]] = ()

    @classmethod
    def from_supabase(cls, data: SupabaseRow) -> Self:
        if cls.required_fields:
            validate_supabase_row(data, list(cls.required_fields))
        return cls(**data)
