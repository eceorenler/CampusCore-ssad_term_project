"""Staff-verified QR check-in (spec R5, R6 and POST /check-ins/verify)."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import AppError
from app.core.security import sha256_hex
from app.db.models import CheckIn, Reservation, ReservationStatus, User
from app.modules.reservations.rules import GRACE


def _invalid_qr(message: str = "QR code is not valid.") -> AppError:
    return AppError(400, "INVALID_QR", message)


def verify(db: Session, staff: User, qr_token: str, resource_id: int) -> tuple[Reservation, CheckIn, User]:
    """Checks in the decision-table order: valid QR + matching resource, not own reservation,
    status CONFIRMED, start <= now <= start + 15 min (inclusive). All in one transaction,
    with the reservation row locked so a concurrent no-show update cannot interleave.
    """
    try:
        reservation = db.scalar(
            select(Reservation).where(Reservation.qr_token_hash == sha256_hex(qr_token.strip())).with_for_update()
        )
        if reservation is None:
            raise _invalid_qr()
        if reservation.resource_id != resource_id:
            raise _invalid_qr("This QR code belongs to a different resource.")
        if reservation.user_id == staff.id:
            raise AppError(409, "SELF_CHECK_IN_FORBIDDEN", "Staff cannot verify their own reservation.")
        if reservation.status != ReservationStatus.CONFIRMED.value:
            raise AppError(409, "INVALID_STATUS", f"Reservation is {reservation.status}; check-in is not possible.")

        now = clock.utcnow()
        if now < reservation.start_time:
            raise AppError(409, "CHECK_IN_WINDOW_CLOSED", "Check-in opens at the reservation start time.")
        if now > reservation.start_time + GRACE:
            # Spec section 10: "QR after grace period -> rejected; no-show processed".
            reservation.status = ReservationStatus.NO_SHOW.value
            db.commit()
            raise AppError(409, "CHECK_IN_WINDOW_CLOSED", "The 15-minute check-in period has ended.")

        check_in = CheckIn(reservation_id=reservation.id, verified_by=staff.id, checked_in_at=now)
        reservation.status = ReservationStatus.CHECKED_IN.value
        db.add(check_in)
        db.flush()
        holder = db.get(User, reservation.user_id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(409, "INVALID_STATUS", "This reservation is already checked in.") from exc
    except Exception:
        db.rollback()
        raise
    return reservation, check_in, holder
