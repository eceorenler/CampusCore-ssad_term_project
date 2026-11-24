"""Shared FastAPI dependencies: current user, role checks and CSRF (spec section 7).

Usage in a router:
    user: CurrentUser                                   -> any logged-in user
    user: User = Depends(require_roles(Role.STAFF))     -> role check (403 otherwise)
    dependencies=[Depends(csrf_protect)]                -> state-changing request
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, Request
from fastapi.security import APIKeyCookie, APIKeyHeader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import constant_time_equals, csrf_token_for, sha256_hex
from app.db.models import Role, User, UserSession
from app.db.session import get_db

settings = get_settings()

# Declared as security schemes so Swagger (/api/v1/docs) shows them under "Authorize".
_session_cookie = APIKeyCookie(name=settings.session_cookie, auto_error=False)
_csrf_header = APIKeyHeader(name=settings.csrf_header_name, auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


@dataclass
class AuthContext:
    user: User
    session: UserSession
    session_token: str  # raw cookie value, needed to derive the CSRF token


def _unauthenticated() -> AppError:
    return AppError(401, "UNAUTHENTICATED", "Authentication required.")


def get_auth_context(db: DbSession, token: Annotated[str | None, Depends(_session_cookie)]) -> AuthContext:
    """Valid session = known token hash, not revoked, not expired (fixed 8 h), user active."""
    if not token:
        raise _unauthenticated()

    now = clock.utcnow()
    row = db.execute(
        select(UserSession, User)
        .join(User, User.id == UserSession.user_id)
        .where(
            UserSession.session_token_hash == sha256_hex(token),
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
            User.is_active.is_(True),
        )
    ).first()
    if row is None:
        raise _unauthenticated()
    session, user = row

    # Informational only; the 8-hour expiry is absolute and never extended (R11).
    stale = timedelta(seconds=settings.session_last_seen_update_seconds)
    if session.last_seen_at is None or now - session.last_seen_at > stale:
        session.last_seen_at = now
        db.commit()

    return AuthContext(user=user, session=session, session_token=token)


def get_current_user(ctx: Annotated[AuthContext, Depends(get_auth_context)]) -> User:
    return ctx.user


CurrentAuth = Annotated[AuthContext, Depends(get_auth_context)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: Role):
    """Dependency factory: 403 FORBIDDEN unless the user has one of the roles.

    The role always comes from the database via the session, never from the client (spec section 4).
    """
    allowed = {r.value for r in roles}

    def _check(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise AppError(403, "FORBIDDEN", "You do not have permission for this action.")
        return user

    return _check


# ---------- CSRF ----------

def _trusted_origins(request: Request) -> set[str]:
    own = f"{request.url.scheme}://{request.url.netloc}"
    return {own, *settings.cors_origins}


def verify_origin(request: Request) -> None:
    """Reject cross-site state-changing requests by Origin/Referer when the browser sends one."""
    origin = request.headers.get("origin")
    if origin is None:
        referer = request.headers.get("referer")
        if referer:
            parts = urlsplit(referer)
            origin = f"{parts.scheme}://{parts.netloc}"
    if origin is not None and origin not in _trusted_origins(request):
        raise AppError(403, "CSRF_FAILED", "Request origin is not allowed.")


def csrf_protect(
    request: Request,
    ctx: CurrentAuth,
    header_token: Annotated[str | None, Depends(_csrf_header)],
) -> None:
    """Required on every authenticated POST/PATCH/DELETE (spec section 7).

    The client receives the token from POST /auth/login or GET /auth/me (field "csrf_token")
    and sends it back in the X-CSRF-Token header.
    """
    verify_origin(request)
    expected = csrf_token_for(ctx.session_token)
    if not header_token or not constant_time_equals(header_token, expected):
        raise AppError(403, "CSRF_FAILED", "CSRF token missing or invalid.")
