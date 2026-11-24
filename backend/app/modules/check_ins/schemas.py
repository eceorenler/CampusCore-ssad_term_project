from pydantic import BaseModel, Field

from app.core.api_types import ApiDateTime


class VerifyRequest(BaseModel):
    qr_token: str = Field(min_length=1, max_length=200)
    # The resource the staff member is standing at; the QR must belong to it.
    resource_id: int


class VerifyResponse(BaseModel):
    reservation_id: int
    status: str
    checked_in_at: ApiDateTime
    # Lets staff compare the reservation holder with the person (e.g. student ID card),
    # since a QR image alone could be shared.
    holder_name: str
