from datetime import date as Date
from datetime import time
from typing import Literal

from pydantic import AwareDatetime, BaseModel


class ResourceSummary(BaseModel):
    id: int
    name: str
    type: str
    location: str | None
    capacity: int | None
    is_active: bool


class ResourceDetail(ResourceSummary):
    description: str | None
    # Daily opening hours, local Europe/Istanbul time (frontend shows them on the calendar).
    opens_at: time
    closes_at: time


class OccupiedInterval(BaseModel):
    type: Literal["RESERVATION", "RESOURCE_CLOSURE"]
    start_time: str  # ISO 8601 in the requested timezone
    end_time: str


class OccupiedResponse(BaseModel):
    """No owner names, user IDs, reservation IDs or QR data (spec section 5 / privacy)."""

    resource_id: int
    date: Date
    timezone: str
    opens_at: time
    closes_at: time
    occupied_intervals: list[OccupiedInterval]


class AvailabilityQuery(BaseModel):
    start_time: AwareDatetime
    end_time: AwareDatetime


class AvailabilityResponse(BaseModel):
    resource_id: int
    available: bool
    # null when available; otherwise RESOURCE_INACTIVE, OUTSIDE_OPENING_HOURS,
    # RESOURCE_CLOSED or RESERVATION_CONFLICT.
    reason: str | None
