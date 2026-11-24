"""GET /resources, /resources/{id}, /resources/{id}/occupied, /resources/{id}/availability."""

from datetime import date as Date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.api_types import Page, PageParams
from app.core.config import get_settings
from app.core.dependencies import CurrentUser, DbSession
from app.modules.resources import service
from app.modules.resources.schemas import (
    AvailabilityQuery,
    AvailabilityResponse,
    OccupiedResponse,
    ResourceDetail,
    ResourceSummary,
)

router = APIRouter(prefix="/resources", tags=["resources"])


@router.get("", response_model=Page[ResourceSummary])
def list_resources(
    user: CurrentUser,
    db: DbSession,
    paging: Annotated[PageParams, Depends()],
    type: Annotated[str | None, Query(max_length=30)] = None,
):
    items, total = service.list_resources(db, user, type, paging.offset, paging.page_size)
    return Page[ResourceSummary](
        items=[ResourceSummary.model_validate(r, from_attributes=True) for r in items],
        page=paging.page, page_size=paging.page_size, total=total,
    )


@router.get("/{resource_id}", response_model=ResourceDetail)
def get_resource(resource_id: int, user: CurrentUser, db: DbSession):
    return ResourceDetail.model_validate(service.get_visible_resource(db, user, resource_id), from_attributes=True)


@router.get("/{resource_id}/occupied", response_model=OccupiedResponse)
def occupied(
    resource_id: int,
    user: CurrentUser,
    db: DbSession,
    date: Annotated[Date, Query()],
    timezone: Annotated[str, Query(max_length=64)] = get_settings().campus_timezone,
):
    return service.occupied(db, user, resource_id, date, timezone)


@router.get("/{resource_id}/availability", response_model=AvailabilityResponse)
def availability(resource_id: int, user: CurrentUser, db: DbSession, q: Annotated[AvailabilityQuery, Query()]):
    return service.availability(db, user, resource_id, q.start_time, q.end_time)
