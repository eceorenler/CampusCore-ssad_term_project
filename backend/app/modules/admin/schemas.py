from datetime import time

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.core.api_types import ApiDateTime
from app.db.models import Role


def _check_hours(opens_at: time | None, closes_at: time | None) -> None:
    if opens_at is not None and closes_at is not None and opens_at >= closes_at:
        raise ValueError("opens_at must be earlier than closes_at (same-day schedule)")


# ---------- resources ----------

class ResourceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    type: str = Field(min_length=1, max_length=30)
    location: str | None = Field(default=None, max_length=150)
    capacity: int | None = Field(default=None, gt=0)
    description: str | None = None
    # Local Europe/Istanbul wall-clock times, e.g. "08:00:00".
    opens_at: time
    closes_at: time

    @model_validator(mode="after")
    def _hours(self):
        _check_hours(self.opens_at, self.closes_at)
        return self


class ResourceUpdate(BaseModel):
    """Partial update. is_active is changed only through /deactivate (spec section 5)."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    type: str | None = Field(default=None, min_length=1, max_length=30)
    location: str | None = Field(default=None, max_length=150)
    capacity: int | None = Field(default=None, gt=0)
    description: str | None = None
    opens_at: time | None = None
    closes_at: time | None = None

    @model_validator(mode="after")
    def _hours(self):
        _check_hours(self.opens_at, self.closes_at)
        return self


class ResourceDeactivated(BaseModel):
    id: int
    is_active: bool


# ---------- scheduled closures ----------

class ClosureCreate(BaseModel):
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    reason: str | None = Field(default=None, max_length=255)


class ClosureItem(BaseModel):
    id: int
    starts_at: ApiDateTime
    ends_at: ApiDateTime
    reason: str | None


class ClosureList(BaseModel):
    items: list[ClosureItem]


class ClosureCreated(BaseModel):
    id: int
    resource_id: int
    cancelled_reservation_ids: list[int]
    # Already-started or CHECKED_IN overlaps: not changed automatically, ADMIN handles them.
    requires_manual_review_ids: list[int]


# ---------- reservations, usage, users ----------

class AdminReservationItem(BaseModel):
    id: int
    user_id: int
    resource_id: int
    status: str
    start_time: ApiDateTime
    end_time: ApiDateTime
    cancellation_reason: str | None


class UsageResponse(BaseModel):
    """Exactly the five lifetime counts of spec v1.3 (no date filters, no advanced analytics)."""

    total_reservations: int
    checked_in: int
    cancelled: int
    no_show: int
    total_resources: int


class AdminUserItem(BaseModel):
    """Never includes password hashes or session data."""

    id: int
    full_name: str
    email: str
    role: str
    is_active: bool
    created_at: ApiDateTime


class RoleChange(BaseModel):
    role: Role


class RoleChanged(BaseModel):
    id: int
    role: str
