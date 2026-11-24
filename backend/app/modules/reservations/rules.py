"""Booking rules shared by the availability preview, booking creation and check-in.

All intervals are half-open [start, end) (spec section 2).
"""

from datetime import datetime, timedelta

from sqlalchemy import and_, exists, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models import Reservation, ReservationStatus, Resource, ResourceUnavailability

settings = get_settings()

GRACE = timedelta(minutes=settings.check_in_grace_minutes)
MAX_DURATION = timedelta(minutes=settings.max_reservation_minutes)


def validate_interval(start: datetime, end: datetime, now: datetime) -> None:
    """R1: 0 < duration <= 120 minutes and the start is in the future. Raises 400."""
    if end <= start or end - start > MAX_DURATION:
        raise AppError(400, "INVALID_DURATION",
                       f"Reservation must end after it starts and last at most {settings.max_reservation_minutes} minutes.")
    if start <= now:
        # Not in the spec's error table; R1 requires a future start (400 = invalid business rule).
        raise AppError(400, "START_TIME_IN_PAST", "Reservation start time must be in the future.")


def within_opening_hours(resource: Resource, start: datetime, end: datetime) -> bool:
    """R2: inside the resource's daily Europe/Istanbul opening window, on a single day."""
    tz = settings.campus_tz
    local_start, local_end = start.astimezone(tz), end.astimezone(tz)
    if local_start.date() != local_end.date():
        return False  # same-day schedule only in v1; also rejects ending at/after midnight
    return resource.opens_at <= local_start.time() and local_end.time() <= resource.closes_at


def overlaps_closure(db: Session, resource_id: int, start: datetime, end: datetime) -> bool:
    """R10: half-open overlap with an ADMIN-scheduled closure."""
    return db.scalar(select(exists().where(
        ResourceUnavailability.resource_id == resource_id,
        ResourceUnavailability.starts_at < end,
        ResourceUnavailability.ends_at > start,
    )))


def blocking_reservation_filter(now: datetime):
    """Reservations that occupy their slot: CHECKED_IN, or CONFIRMED whose grace period has not ended.

    A CONFIRMED reservation past start + 15 min is a no-show waiting for the job (R7), so its
    time is already treated as released.
    """
    return or_(
        Reservation.status == ReservationStatus.CHECKED_IN.value,
        and_(Reservation.status == ReservationStatus.CONFIRMED.value, Reservation.start_time + GRACE >= now),
    )


def overlaps_reservation(db: Session, resource_id: int, start: datetime, end: datetime, now: datetime) -> bool:
    return db.scalar(select(exists().where(
        Reservation.resource_id == resource_id,
        Reservation.start_time < end,
        Reservation.end_time > start,
        blocking_reservation_filter(now),
    )))


def mark_no_shows(db: Session, now: datetime, resource_id: int | None = None) -> list[int]:
    """R7: CONFIRMED reservations with now > start + 15 min become NO_SHOW. Caller commits.

    A conditional UPDATE (WHERE status = 'CONFIRMED') is safe against a concurrent check-in:
    whichever commits first wins, the other matches zero rows (spec section 8).
    """
    stmt = (
        update(Reservation)
        .where(Reservation.status == ReservationStatus.CONFIRMED.value, Reservation.start_time + GRACE < now)
        .values(status=ReservationStatus.NO_SHOW.value)
        .returning(Reservation.id)
        .execution_options(synchronize_session=False)
    )
    if resource_id is not None:
        stmt = stmt.where(Reservation.resource_id == resource_id)
    return list(db.scalars(stmt))
