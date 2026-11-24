"""POST /auth/login, POST /auth/logout, GET /auth/me (spec section 5)."""

from fastapi import APIRouter, Depends, Request, Response, status

from app.core.config import get_settings
from app.core.dependencies import CurrentAuth, DbSession, csrf_protect, verify_origin
from app.core.security import csrf_token_for
from app.modules.auth import service
from app.modules.auth.schemas import LoginRequest, LoginResponse, MeResponse

settings = get_settings()
router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str) -> None:
    # Spec section 7: HttpOnly, Secure (HTTPS), Path=/, SameSite=Lax, no Domain attribute.
    response.set_cookie(
        key=settings.session_cookie,
        value=token,
        max_age=settings.session_lifetime_hours * 3600,
        path="/",
        secure=settings.is_production,
        httponly=True,
        samesite="lax",
    )


@router.post("/login", response_model=LoginResponse, dependencies=[Depends(verify_origin)])
def login(body: LoginRequest, request: Request, response: Response, db: DbSession):
    client_ip = request.client.host if request.client else "unknown"
    previous = request.cookies.get(settings.session_cookie)
    user, token = service.login(db, body.email, body.password, client_ip, previous)
    _set_session_cookie(response, token)
    return LoginResponse(id=user.id, full_name=user.full_name, role=user.role, csrf_token=csrf_token_for(token))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(csrf_protect)])
def logout(ctx: CurrentAuth, db: DbSession):
    service.logout(db, ctx.session)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(settings.session_cookie, path="/", secure=settings.is_production,
                           httponly=True, samesite="lax")
    return response


@router.get("/me", response_model=MeResponse)
def me(ctx: CurrentAuth):
    u = ctx.user
    return MeResponse(id=u.id, full_name=u.full_name, email=u.email, role=u.role, is_active=u.is_active,
                      csrf_token=csrf_token_for(ctx.session_token))
