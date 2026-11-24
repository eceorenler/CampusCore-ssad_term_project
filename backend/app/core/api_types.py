"""Shared API types: date-time output format and pagination (spec section 4)."""

from datetime import datetime
from typing import Annotated, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel, PlainSerializer

from app.core.config import get_settings


def to_campus_iso(value: datetime) -> str:
    """UTC from the database -> ISO 8601 with the campus offset, e.g. 2026-11-20T10:00:00+03:00."""
    return value.astimezone(get_settings().campus_tz).isoformat(timespec="seconds")


# Use for every datetime in a response model.
ApiDateTime = Annotated[datetime, PlainSerializer(to_campus_iso, return_type=str)]


class PageParams:
    """page (default 1), page_size (default 20, max 100)."""

    def __init__(
        self,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    ):
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int
