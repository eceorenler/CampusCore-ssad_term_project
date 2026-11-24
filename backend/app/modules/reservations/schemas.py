from pydantic import AwareDatetime, BaseModel

from app.core.api_types import ApiDateTime


class ReservationCreate(BaseModel):
    # Never accept user_id / role from the client: the owner is the logged-in user (spec section 4).
    resource_id: int
    start_time: AwareDatetime  # ISO 8601 with offset, e.g. 2026-11-20T10:00:00+03:00
    end_time: AwareDatetime


class ReservationCreated(BaseModel):
    id: int
    resource_id: int
    start_time: ApiDateTime
    end_time: ApiDateTime
    status: str
    qr_available: bool


class ReservationListItem(BaseModel):
    id: int
    resource_id: int
    status: str
    start_time: ApiDateTime
    end_time: ApiDateTime
    # e.g. RESOURCE_CLOSURE, so the frontend can explain why a booking was cancelled.
    cancellation_reason: str | None


class ReservationDetail(BaseModel):
    """No raw QR token here (spec section 5); use GET /reservations/{id}/qr."""

    id: int
    resource_id: int
    user_id: int
    status: str
    start_time: ApiDateTime
    end_time: ApiDateTime
    created_at: ApiDateTime
    cancellation_reason: str | None


class ReservationCancelled(BaseModel):
    id: int
    status: str


class ReservationQr(BaseModel):
    reservation_id: int
    qr_payload: str
    status: str
