"""Login / logout business logic (spec sections 5 and 7)."""

from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import DUMMY_PASSWORD_HASH, new_token, sha256_hex, verify_password
from app.db.models import User, UserSession
from app.modules.auth.rate_limit import login_rate_limiter

settings = get_settings()

def _invalid_login() -> AppError:
    return AppError(401, "UNAUTHENTICATED", "Invalid email or password.")


def login(db: Session, email: str, password: str, client_ip: str, previous_token: str | None) -> tuple[User, str]:
    """Return (user, new raw session token). Raises 401 / 429.

    The failure message is identical for unknown email, wrong password and inactive
    account, so the response never reveals whether an email exists.
    """
    if login_rate_limiter.is_blocked(client_ip, email):
        raise AppError(429, "RATE_LIMITED", "Too many login attempts. Try again later.")

    user = db.scalar(select(User).where(func.lower(User.email) == email.strip().lower()))
    # Verify against a dummy hash when the user does not exist so timing is similar.
    password_ok = verify_password(password, user.password_hash if user else DUMMY_PASSWORD_HASH)
    if user is None or not password_ok or not user.is_active:
        login_rate_limiter.record_failure(client_ip, email)
        raise _invalid_login()

    login_rate_limiter.reset(client_ip, email)
    now = clock.utcnow()

    # Session rotation: a session cookie presented at login is revoked, a new one is issued.
    if previous_token:
        _revoke_by_token(db, previous_token, now)

    token = new_token()
    db.add(UserSession(
        user_id=user.id,
        session_token_hash=sha256_hex(token),
        created_at=now,
        expires_at=now + timedelta(hours=settings.session_lifetime_hours),  # absolute, no sliding
        last_seen_at=now,
    ))
    db.commit()
    return user, token


def logout(db: Session, session: UserSession) -> None:
    session.revoked_at = clock.utcnow()
    db.commit()


def revoke_all_sessions(db: Session, user_id: int) -> None:
    """Used after a role change (spec: revoke existing sessions). Caller commits."""
    db.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=clock.utcnow())
    )


def _revoke_by_token(db: Session, token: str, now) -> None:
    db.execute(
        update(UserSession)
        .where(UserSession.session_token_hash == sha256_hex(token), UserSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
