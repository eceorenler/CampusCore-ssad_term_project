"""ADMIN management: resources, scheduled closures, reservations, usage counts, roles (spec R9, R10)."""

import logging
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import AppError
from app.db.models import Reservation, ReservationStatus, Resource, ResourceUnavailability, Role, User
from app.modules.admin.schemas import ResourceCreate, ResourceUpdate
from app.modules.auth.service import revoke_all_sessions
from app.modules.reservations import rules

audit_log = logging.getLogger("campuscore.audit")


def _resource_not_found() -> AppError:
    return AppError(404, "NOT_FOUND", "Resource not found.")


def _get_resource_for_update(db: Session, resource_id: int) -> Resource:
    resource = db.scalar(select(Resource).where(Resource.id == resource_id).with_for_update())
    if resource is None:
        raise _resource_not_found()
    return resource


# ---------- resources ----------

def create_resource(db: Session, data: ResourceCreate) -> Resource:
    resource = Resource(**data.model_dump())
    db.add(resource)
    db.commit()
    db.refresh(resource)
    return resource


def update_resource(db: Session, resource_id: int, data: ResourceUpdate) -> Resource:
    """Partial update. Changing opening hours does not cancel existing bookings (spec section 5)."""
    try:
        resource = _get_resource_for_update(db, resource_id)
        changes = data.model_dump(exclude_unset=True)
        for field in ("name", "type", "opens_at", "closes_at"):
            if field in changes and changes[field] is None:
                raise AppError(422, "VALIDATION_ERROR", f"{field}: may not be null")
        opens = changes.get("opens_at", resource.opens_at)
        closes = changes.get("closes_at", resource.closes_at)
        if opens >= closes:
            raise AppError(422, "VALIDATION_ERROR", "opens_at must be earlier than closes_at (same-day schedule)")
        for field, value in changes.items():
            setattr(resource, field, value)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return resource


def deactivate_resource(db: Session, resource_id: int) -> Resource:
    """Blocks new bookings; existing bookings stay as they are (spec section 2 / 11)."""
    try:
        resource = _get_resource_for_update(db, resource_id)
        resource.is_active = False
        db.commit()
    except Exception:
        db.rollback()
        raise
    return resource


# ---------- scheduled closures ----------

def list_closures(db: Session, resource_id: int) -> list[ResourceUnavailability]:
    if db.get(Resource, resource_id) is None:
        raise _resource_not_found()
    return list(db.scalars(
        select(ResourceUnavailability)
        .where(ResourceUnavailability.resource_id == resource_id)
        .order_by(ResourceUnavailability.starts_at, ResourceUnavailability.id)
    ))


def create_closure(db: Session, admin: User, resource_id: int, starts_at: datetime, ends_at: datetime,
                   reason: str | None) -> tuple[ResourceUnavailability, list[int], list[int]]:
    """R10, in one transaction with the resource row locked (serializes with new bookings):
    insert the closure, cancel overlapping future CONFIRMED bookings (incl. partial overlap),
    and report already-started / CHECKED_IN overlaps for manual review.
    """
    now = clock.utcnow()
    if ends_at <= starts_at:
        raise AppError(400, "INVALID_INTERVAL", "ends_at must be after starts_at.")
    if starts_at <= now:
        raise AppError(400, "INVALID_INTERVAL", "A closure must start in the future.")

    try:
        _get_resource_for_update(db, resource_id)
        rules.mark_no_shows(db, now, resource_id=resource_id)

        closure = ResourceUnavailability(resource_id=resource_id, starts_at=starts_at, ends_at=ends_at,
                                         reason=reason, created_by=admin.id)
        db.add(closure)

        overlapping = db.scalars(
            select(Reservation).where(
                Reservation.resource_id == resource_id,
                Reservation.status.in_([ReservationStatus.CONFIRMED.value, ReservationStatus.CHECKED_IN.value]),
                Reservation.start_time < ends_at,
                Reservation.end_time > starts_at,
            ).order_by(Reservation.start_time).with_for_update()
        ).all()

        cancelled, manual_review = [], []
        for r in overlapping:
            if r.status == ReservationStatus.CONFIRMED.value and r.start_time > now:
                r.status = ReservationStatus.CANCELLED.value
                r.cancellation_reason = "RESOURCE_CLOSURE"
                cancelled.append(r.id)
            else:
                manual_review.append(r.id)

        db.flush()
        db.commit()
    except Exception:
        db.rollback()
        raise

    audit_log.info("closure created id=%s resource=%s by admin=%s cancelled=%s manual_review=%s",
                   closure.id, resource_id, admin.id, cancelled, manual_review)
    return closure, cancelled, manual_review


# ---------- reservations and usage ----------

def list_reservations(db: Session, resource_id: int | None, status: ReservationStatus | None,
                      start_from: datetime | None, start_to: datetime | None, offset: int, limit: int):
    query = select(Reservation)
    if resource_id is not None:
        query = query.where(Reservation.resource_id == resource_id)
    if status is not None:
        query = query.where(Reservation.status == status.value)
    if start_from is not None:
        query = query.where(Reservation.start_time >= start_from)
    if start_to is not None:
        query = query.where(Reservation.start_time < start_to)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.order_by(Reservation.start_time.desc(), Reservation.id.desc()).offset(offset).limit(limit))
    return list(items), total


def usage(db: Session) -> dict[str, int]:
    counts = dict(db.execute(select(Reservation.status, func.count()).group_by(Reservation.status)).all())
    return {
        "total_reservations": sum(counts.values()),
        "checked_in": counts.get(ReservationStatus.CHECKED_IN.value, 0),
        "cancelled": counts.get(ReservationStatus.CANCELLED.value, 0),
        "no_show": counts.get(ReservationStatus.NO_SHOW.value, 0),
        "total_resources": db.scalar(select(func.count()).select_from(Resource)),
    }


# ---------- users ----------

def list_users(db: Session, search: str | None, role: Role | None, offset: int, limit: int):
    """All users (active and inactive), optionally filtered by role and a name/email search."""
    query = select(User)
    if role is not None:
        query = query.where(User.role == role.value)
    if search:
        # Escape LIKE wildcards so the search is a plain "contains" match.
        escaped = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        query = query.where(or_(User.full_name.ilike(pattern, escape="\\"), User.email.ilike(pattern, escape="\\")))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.order_by(User.full_name, User.id).offset(offset).limit(limit))
    return list(items), total


def change_role(db: Session, admin: User, user_id: int, new_role: Role) -> User:
    """Audited; never removes the last active ADMIN; revokes the user's sessions after a change."""
    try:
        # Lock all active admins so two simultaneous demotions cannot both pass the check.
        active_admin_ids = set(db.scalars(
            select(User.id).where(User.role == Role.ADMIN.value, User.is_active.is_(True)).with_for_update()
        ))
        target = db.scalar(select(User).where(User.id == user_id).with_for_update())
        if target is None:
            raise AppError(404, "NOT_FOUND", "User not found.")

        old_role = target.role
        if old_role == new_role.value:
            db.rollback()
            return target
        if target.id in active_admin_ids and len(active_admin_ids) <= 1:
            raise AppError(409, "LAST_ADMIN", "The last active administrator cannot be demoted.")

        target.role = new_role.value
        revoke_all_sessions(db, target.id)
        db.commit()
    except Exception:
        db.rollback()
        raise

    audit_log.info("role change user=%s %s -> %s by admin=%s", target.id, old_role, new_role.value, admin.id)
    return target
