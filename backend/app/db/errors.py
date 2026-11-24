"""Helpers for reading PostgreSQL constraint violations."""

from sqlalchemy.exc import IntegrityError


def violated_constraint(exc: IntegrityError) -> str | None:
    """Name of the constraint PostgreSQL reported, e.g. "no_active_overlap"."""
    diag = getattr(exc.orig, "diag", None)
    name = getattr(diag, "constraint_name", None)
    if name:
        return name
    # Fallback: search the message text.
    text = str(exc.orig)
    for known in ("no_active_overlap", "uq_check_ins_reservation_id", "uq_reservations_qr_token_hash"):
        if known in text:
            return known
    return None
