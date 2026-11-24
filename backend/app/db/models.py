"""SQLAlchemy models for the six CampusCore tables (spec v1.3, section 3).

The tables themselves are created by the Alembic migration in
migrations/versions/0001_initial_schema.py. These models mirror it.

Rules enforced in the database (not only in Python):
- case-insensitive unique email
- role / status values, capacity > 0, opens_at < closes_at
- end_time > start_time and duration <= 120 minutes
- no overlapping CONFIRMED / CHECKED_IN reservations for one resource
  (GiST exclusion constraint "no_active_overlap", created in the migration;
  SQLAlchemy does not need to know about it, but the reservation service
  must catch its violation and return 409 RESERVATION_CONFLICT)
- at most one check-in per reservation
- no cascading deletes: booking and closure history is never removed
"""

from datetime import datetime, time
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    Time,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Role(StrEnum):
    STUDENT = "STUDENT"
    STAFF = "STAFF"
    ADMIN = "ADMIN"


class ReservationStatus(StrEnum):
    CONFIRMED = "CONFIRMED"
    CHECKED_IN = "CHECKED_IN"  # terminal (R8)
    CANCELLED = "CANCELLED"  # terminal (R8)
    NO_SHOW = "NO_SHOW"  # terminal (R8)


# Statuses that occupy a time slot (R3).
ACTIVE_STATUSES = (ReservationStatus.CONFIRMED, ReservationStatus.CHECKED_IN)


def _in_list(column: str, values: type[StrEnum]) -> str:
    return f"{column} IN ({', '.join(repr(v.value) for v in values)})"


def _id() -> Mapped[int]:
    return mapped_column(BigInteger, Identity(), primary_key=True)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = _id()
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)  # Argon2id
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = _created_at()

    sessions: Mapped[list["UserSession"]] = relationship(back_populates="user")
    reservations: Mapped[list["Reservation"]] = relationship(back_populates="user")

    __table_args__ = (
        CheckConstraint(_in_list("role", Role), name="role"),
        Index("uq_users_email_lower", text("lower(email)"), unique=True),
    )


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[int] = _id()
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    # Only the SHA-256 hex digest of the cookie token is stored (spec section 7).
    session_token_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = _created_at()
    # created_at + 8 hours, fixed, no sliding extension (R11).
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="sessions")

    __table_args__ = (CheckConstraint("expires_at > created_at", name="expires_after_created"),)


class Resource(Base):
    __tablename__ = "resources"

    id: Mapped[int] = _id()
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(30), nullable=False)  # e.g. STUDY_ROOM, LAB, EQUIPMENT
    description: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(150))
    capacity: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    # Local Europe/Istanbul wall-clock times, same-day only in v1.
    opens_at: Mapped[time] = mapped_column(Time, nullable=False)
    closes_at: Mapped[time] = mapped_column(Time, nullable=False)
    created_at: Mapped[datetime] = _created_at()

    reservations: Mapped[list["Reservation"]] = relationship(back_populates="resource")
    closures: Mapped[list["ResourceUnavailability"]] = relationship(back_populates="resource")

    __table_args__ = (
        CheckConstraint("capacity IS NULL OR capacity > 0", name="capacity_positive"),
        CheckConstraint("opens_at < closes_at", name="opening_hours"),
    )


class Reservation(Base):
    __tablename__ = "reservations"

    id: Mapped[int] = _id()
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    resource_id: Mapped[int] = mapped_column(ForeignKey("resources.id", ondelete="RESTRICT"), nullable=False)
    # Half-open interval [start_time, end_time), stored in UTC.
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text(f"'{ReservationStatus.CONFIRMED.value}'")
    )
    # SHA-256 digest for lookup + AES-GCM ciphertext so the owner can re-display the same QR.
    qr_token_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False, unique=True)
    qr_token_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created_at()
    cancellation_reason: Mapped[str | None] = mapped_column(String(40))  # e.g. USER, RESOURCE_CLOSURE

    user: Mapped[User] = relationship(back_populates="reservations")
    resource: Mapped[Resource] = relationship(back_populates="reservations")
    check_in: Mapped["CheckIn | None"] = relationship(back_populates="reservation")

    __table_args__ = (
        CheckConstraint(_in_list("status", ReservationStatus), name="status"),
        CheckConstraint("end_time > start_time", name="time_order"),
        CheckConstraint("end_time - start_time <= interval '120 minutes'", name="max_duration"),
        Index("ix_reservations_user_id_start_time", "user_id", "start_time"),
        Index("ix_reservations_resource_id_start_time", "resource_id", "start_time"),
        Index("ix_reservations_status_start_time", "status", "start_time"),
        # The GiST exclusion constraint "no_active_overlap" is created in the migration.
    )


class CheckIn(Base):
    __tablename__ = "check_ins"

    id: Mapped[int] = _id()
    reservation_id: Mapped[int] = mapped_column(
        ForeignKey("reservations.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    verified_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    checked_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    reservation: Mapped[Reservation] = relationship(back_populates="check_in")


class ResourceUnavailability(Base):
    __tablename__ = "resource_unavailability"

    id: Mapped[int] = _id()
    resource_id: Mapped[int] = mapped_column(ForeignKey("resources.id", ondelete="RESTRICT"), nullable=False)
    # Half-open interval [starts_at, ends_at).
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = _created_at()

    resource: Mapped[Resource] = relationship(back_populates="closures")

    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="time_order"),
        Index("ix_resource_unavailability_resource_id_starts_at", "resource_id", "starts_at"),
    )
