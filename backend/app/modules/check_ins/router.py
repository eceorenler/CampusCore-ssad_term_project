"""POST /check-ins/verify (STAFF only)."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.dependencies import DbSession, csrf_protect, require_roles
from app.db.models import Role, User
from app.modules.check_ins import service
from app.modules.check_ins.schemas import VerifyRequest, VerifyResponse

router = APIRouter(prefix="/check-ins", tags=["check-ins"])

# The verifier identity comes from the session, never from the request body.
Staff = Annotated[User, Depends(require_roles(Role.STAFF))]


@router.post("/verify", response_model=VerifyResponse, dependencies=[Depends(csrf_protect)])
def verify_check_in(body: VerifyRequest, staff: Staff, db: DbSession):
    reservation, check_in, holder = service.verify(db, staff, body.qr_token, body.resource_id)
    return VerifyResponse(reservation_id=reservation.id, status=reservation.status,
                          checked_in_at=check_in.checked_in_at, holder_name=holder.full_name)
