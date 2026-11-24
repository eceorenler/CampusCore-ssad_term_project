"""Reservation lifecycle: create, list, read, cancel, QR re-display (spec sections 5 and 8)."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import AppError
from app.core.security import decrypt_qr_token, generate_qr_token
from app.db.errors import violated_constraint
from app.db.models import Reservation, ReservationStatus, Resource, Role, User
from app.modules.reservations import rules


def _not_found() -> AppError:
    # Also used when the reservation exists but belongs to someone else (privacy, spec section 4).
    return AppError(404, "NOT_FOUND", "Reservation not found.")


def _conflict() -> AppError:
    return AppError(409, "RESERVATION_CONFLICT", "The resource is already reserved for the selected time.")


def create(db: Session, user: User, resource_id: int, start: datetime, end: datetime) -> Reservation:
    """Spec section 8 "Booking creation", in one transaction:

    1. lock the resource row (serializes against closure creation),
    2. validate active status, opening hours, closures and duration,
    3. release expired no-shows on this resource,
    4. insert reservation + encrypted QR token; the GiST constraint is the final
       authority for booking-versus-booking races.
    """
    now = clock.utcnow()
    rules.validate_interval(start, end, now)

    try:
        resource = db.scalar(select(Resource).where(Resource.id == resource_id).with_for_update())
        if resource is None:
            raise AppError(404, "NOT_FOUND", "Resource not found.")
        if not resource.is_active:
            raise AppError(409, "RESOURCE_INACTIVE", "This resource is not available for booking.")
        if not rules.within_opening_hours(resource, start, end):
            raise AppError(409, "OUTSIDE_OPENING_HOURS",
                           f"Bookings must be between {resource.opens_at:%H:%M} and {resource.closes_at:%H:%M}.")
        if rules.overlaps_closure(db, resource_id, start, end):
            raise AppError(409, "RESOURCE_CLOSED", "The resource is closed during the selected time.")

        # A missed check-in must not keep blocking the slot until the next job run (R7).
        rules.mark_no_shows(db, now, resource_id=resource_id)

        if rules.overlaps_reservation(db, resource_id, start, end, now):
            raise _conflict()

        _, qr_hash, qr_ciphertext = generate_qr_token()
        reservation = Reservation(
            user_id=user.id, resource_id=resource_id, start_time=start, end_time=end,
            status=ReservationStatus.CONFIRMED.value, qr_token_hash=qr_hash, qr_token_ciphertext=qr_ciphertext,
        )
        db.add(reservation)
        db.flush()
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if violated_constraint(exc) == "no_active_overlap":
            raise _conflict() from exc
        raise
    except Exception:
        db.rollback()
        raise
    return reservation


def list_own(db: Session, user: User, status: ReservationStatus | None, offset: int, limit: int):
    """Own bookings incl. past ones, newest start first."""
    query = select(Reservation).where(Reservation.user_id == user.id)
    if status is not None:
        query = query.where(Reservation.status == status.value)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(query.order_by(Reservation.start_time.desc(), Reservation.id.desc()).offset(offset).limit(limit))
    return list(items), total


def get_for_reader(db: Session, user: User, reservation_id: int) -> Reservation:
    """Owner or ADMIN; anyone else gets 404."""
    reservation = db.get(Reservation, reservation_id)
    if reservation is None or (reservation.user_id != user.id and user.role != Role.ADMIN.value):
        raise _not_found()
    return reservation


def cancel(db: Session, user: User, reservation_id: int) -> Reservation:
    """R4: owner only, CONFIRMED only, strictly before the start time."""
    try:
        reservation = db.scalar(select(Reservation).where(Reservation.id == reservation_id).with_for_update())
        if reservation is None or reservation.user_id != user.id:
            raise _not_found()
        if reservation.status != ReservationStatus.CONFIRMED.value:
            raise AppError(409, "INVALID_STATUS", f"A {reservation.status} reservation cannot be cancelled.")
        if clock.utcnow() >= reservation.start_time:
            raise AppError(409, "CANCELLATION_WINDOW_CLOSED", "Reservations can only be cancelled before they start.")
        reservation.status = ReservationStatus.CANCELLED.value
        reservation.cancellation_reason = "USER"
        db.commit()
    except Exception:
        db.rollback()
        raise
    return reservation


def get_qr(db: Session, user: User, reservation_id: int) -> tuple[Reservation, str]:
    """Owner only, CONFIRMED only. Returns the same token every time (decrypted server-side)."""
    reservation = db.get(Reservation, reservation_id)
    if reservation is None or reservation.user_id != user.id:
        raise _not_found()
    if reservation.status != ReservationStatus.CONFIRMED.value:
        raise AppError(409, "INVALID_STATUS", f"No QR code is available for a {reservation.status} reservation.")
    return reservation, decrypt_qr_token(reservation.qr_token_ciphertext)
