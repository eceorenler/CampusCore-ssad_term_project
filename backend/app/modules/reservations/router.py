"""POST/GET /reservations, GET /reservations/{id}, POST /reservations/{id}/cancel, GET /reservations/{id}/qr."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.core.api_types import Page, PageParams
from app.core.dependencies import CurrentUser, DbSession, csrf_protect, require_roles
from app.db.models import ReservationStatus, Role, User
from app.modules.reservations import service
from app.modules.reservations.schemas import (
    ReservationCancelled,
    ReservationCreate,
    ReservationCreated,
    ReservationDetail,
    ReservationListItem,
    ReservationQr,
)

router = APIRouter(prefix="/reservations", tags=["reservations"])

# R2 / R9: STUDENT and STAFF can book; ADMIN is management-only and gets 403.
Booker = Annotated[User, Depends(require_roles(Role.STUDENT, Role.STAFF))]


@router.post("", response_model=ReservationCreated, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(csrf_protect)])
def create_reservation(body: ReservationCreate, user: Booker, db: DbSession):
    r = service.create(db, user, body.resource_id, body.start_time, body.end_time)
    return ReservationCreated(id=r.id, resource_id=r.resource_id, start_time=r.start_time, end_time=r.end_time,
                              status=r.status, qr_available=True)


@router.get("", response_model=Page[ReservationListItem])
def list_my_reservations(
    user: Booker,
    db: DbSession,
    paging: Annotated[PageParams, Depends()],
    status: ReservationStatus | None = None,
):
    items, total = service.list_own(db, user, status, paging.offset, paging.page_size)
    return Page[ReservationListItem](
        items=[ReservationListItem.model_validate(r, from_attributes=True) for r in items],
        page=paging.page, page_size=paging.page_size, total=total,
    )


@router.get("/{reservation_id}", response_model=ReservationDetail)
def get_reservation(reservation_id: int, user: CurrentUser, db: DbSession):
    return ReservationDetail.model_validate(service.get_for_reader(db, user, reservation_id), from_attributes=True)


@router.post("/{reservation_id}/cancel", response_model=ReservationCancelled, dependencies=[Depends(csrf_protect)])
def cancel_reservation(reservation_id: int, user: CurrentUser, db: DbSession):
    r = service.cancel(db, user, reservation_id)
    return ReservationCancelled(id=r.id, status=r.status)


@router.get("/{reservation_id}/qr", response_model=ReservationQr)
def get_reservation_qr(reservation_id: int, user: CurrentUser, db: DbSession, response: Response):
    reservation, token = service.get_qr(db, user, reservation_id)
    response.headers["Cache-Control"] = "no-store"  # never cache the QR payload
    return ReservationQr(reservation_id=reservation.id, qr_payload=token, status=reservation.status)
