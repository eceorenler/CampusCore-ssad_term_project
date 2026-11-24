"""Resource catalogue, occupied intervals and availability preview (spec section 5)."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import AppError
from app.db.models import Reservation, Resource, ResourceUnavailability, Role, User
from app.modules.reservations import rules
from app.modules.resources.schemas import AvailabilityResponse, OccupiedInterval, OccupiedResponse


def _not_found() -> AppError:
    return AppError(404, "NOT_FOUND", "Resource not found.")


def list_resources(db: Session, user: User, type_: str | None, offset: int, limit: int) -> tuple[list[Resource], int]:
    """Ordinary users see only active resources; ADMIN also sees inactive ones."""
    query = select(Resource)
    if user.role != Role.ADMIN.value:
        query = query.where(Resource.is_active.is_(True))
    if type_:
        query = query.where(Resource.type == type_)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.order_by(Resource.name, Resource.id).offset(offset).limit(limit)).all()
    return list(items), total


def get_visible_resource(db: Session, user: User, resource_id: int) -> Resource:
    resource = db.get(Resource, resource_id)
    if resource is None or (not resource.is_active and user.role != Role.ADMIN.value):
        raise _not_found()
    return resource


def occupied(db: Session, user: User, resource_id: int, day: date, tz_name: str) -> OccupiedResponse:
    """Booked and closed intervals for one calendar day in the given timezone."""
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise AppError(422, "VALIDATION_ERROR", f"timezone: unknown timezone '{tz_name}'")

    resource = get_visible_resource(db, user, resource_id)
    day_start = datetime.combine(day, time.min, tzinfo=tz)
    day_end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)
    now = clock.utcnow()

    bookings = db.execute(
        select(Reservation.start_time, Reservation.end_time).where(
            Reservation.resource_id == resource_id,
            Reservation.start_time < day_end,
            Reservation.end_time > day_start,
            rules.blocking_reservation_filter(now),
        )
    ).all()
    closures = db.execute(
        select(ResourceUnavailability.starts_at, ResourceUnavailability.ends_at).where(
            ResourceUnavailability.resource_id == resource_id,
            ResourceUnavailability.starts_at < day_end,
            ResourceUnavailability.ends_at > day_start,
        )
    ).all()

    def fmt(value: datetime) -> str:
        return value.astimezone(tz).isoformat(timespec="seconds")

    intervals = [OccupiedInterval(type="RESERVATION", start_time=fmt(s), end_time=fmt(e)) for s, e in bookings]
    intervals += [OccupiedInterval(type="RESOURCE_CLOSURE", start_time=fmt(s), end_time=fmt(e)) for s, e in closures]
    intervals.sort(key=lambda i: i.start_time)

    return OccupiedResponse(resource_id=resource.id, date=day, timezone=tz_name, opens_at=resource.opens_at,
                            closes_at=resource.closes_at, occupied_intervals=intervals)


def availability(db: Session, user: User, resource_id: int, start: datetime, end: datetime) -> AvailabilityResponse:
    """Non-authoritative preview. POST /reservations re-checks everything under a lock."""
    now = clock.utcnow()
    rules.validate_interval(start, end, now)

    resource = db.get(Resource, resource_id)
    if resource is None:
        raise _not_found()

    reason = None
    if not resource.is_active:
        reason = "RESOURCE_INACTIVE"
    elif not rules.within_opening_hours(resource, start, end):
        reason = "OUTSIDE_OPENING_HOURS"
    elif rules.overlaps_closure(db, resource_id, start, end):
        reason = "RESOURCE_CLOSED"
    elif rules.overlaps_reservation(db, resource_id, start, end, now):
        reason = "RESERVATION_CONFLICT"
    return AvailabilityResponse(resource_id=resource_id, available=reason is None, reason=reason)
