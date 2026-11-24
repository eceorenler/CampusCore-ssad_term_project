"""ADMIN-only endpoints under /admin (spec section 5)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from pydantic import AwareDatetime

from app.core.api_types import Page, PageParams
from app.core.dependencies import DbSession, csrf_protect, require_roles
from app.db.models import ReservationStatus, User
from app.db.models import Role as RoleEnum
from app.modules.admin import service
from app.modules.admin.schemas import (
    AdminReservationItem,
    AdminUserItem,
    ClosureCreate,
    ClosureCreated,
    ClosureItem,
    ClosureList,
    ResourceCreate,
    ResourceDeactivated,
    ResourceUpdate,
    RoleChange,
    RoleChanged,
    UsageResponse,
)
from app.modules.resources.schemas import ResourceDetail

Admin = Annotated[User, Depends(require_roles(RoleEnum.ADMIN))]

# Every route here requires ADMIN; state-changing routes additionally require CSRF.
router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_roles(RoleEnum.ADMIN))])
write = [Depends(csrf_protect)]


@router.post("/resources", response_model=ResourceDetail, status_code=status.HTTP_201_CREATED, dependencies=write)
def create_resource(body: ResourceCreate, db: DbSession):
    return ResourceDetail.model_validate(service.create_resource(db, body), from_attributes=True)


@router.patch("/resources/{resource_id}", response_model=ResourceDetail, dependencies=write)
def update_resource(resource_id: int, body: ResourceUpdate, db: DbSession):
    return ResourceDetail.model_validate(service.update_resource(db, resource_id, body), from_attributes=True)


@router.post("/resources/{resource_id}/deactivate", response_model=ResourceDeactivated, dependencies=write)
def deactivate_resource(resource_id: int, db: DbSession):
    r = service.deactivate_resource(db, resource_id)
    return ResourceDeactivated(id=r.id, is_active=r.is_active)


@router.get("/resources/{resource_id}/unavailability", response_model=ClosureList)
def list_closures(resource_id: int, db: DbSession):
    items = service.list_closures(db, resource_id)
    return ClosureList(items=[ClosureItem.model_validate(c, from_attributes=True) for c in items])


@router.post("/resources/{resource_id}/unavailability", response_model=ClosureCreated,
             status_code=status.HTTP_201_CREATED, dependencies=write)
def create_closure(resource_id: int, body: ClosureCreate, admin: Admin, db: DbSession):
    closure, cancelled, manual = service.create_closure(db, admin, resource_id, body.starts_at, body.ends_at,
                                                        body.reason)
    return ClosureCreated(id=closure.id, resource_id=resource_id, cancelled_reservation_ids=cancelled,
                          requires_manual_review_ids=manual)


@router.get("/reservations", response_model=Page[AdminReservationItem])
def list_reservations(
    db: DbSession,
    paging: Annotated[PageParams, Depends()],
    resource_id: int | None = None,
    status: ReservationStatus | None = None,
    start_from: AwareDatetime | None = None,
    start_to: AwareDatetime | None = None,
):
    items, total = service.list_reservations(db, resource_id, status, start_from, start_to,
                                             paging.offset, paging.page_size)
    return Page[AdminReservationItem](
        items=[AdminReservationItem.model_validate(r, from_attributes=True) for r in items],
        page=paging.page, page_size=paging.page_size, total=total,
    )


@router.get("/usage", response_model=UsageResponse)
def usage(db: DbSession):
    return UsageResponse(**service.usage(db))


@router.get("/users", response_model=Page[AdminUserItem])
def list_users(
    db: DbSession,
    paging: Annotated[PageParams, Depends()],
    search: Annotated[str | None, Query(max_length=100)] = None,
    role: RoleEnum | None = None,
):
    items, total = service.list_users(db, search, role, paging.offset, paging.page_size)
    return Page[AdminUserItem](
        items=[AdminUserItem.model_validate(u, from_attributes=True) for u in items],
        page=paging.page, page_size=paging.page_size, total=total,
    )


@router.patch("/users/{user_id}/role", response_model=RoleChanged, dependencies=write)
def change_role(user_id: int, body: RoleChange, admin: Admin, db: DbSession):
    user = service.change_role(db, admin, user_id, body.role)
    return RoleChanged(id=user.id, role=user.role)
