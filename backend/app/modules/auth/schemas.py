from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(BaseModel):
    id: int
    full_name: str
    role: str
    # Send this back in the X-CSRF-Token header on POST/PATCH/DELETE requests.
    # (The session token itself is only in the HttpOnly cookie, never in JSON.)
    csrf_token: str


class MeResponse(BaseModel):
    id: int
    full_name: str
    email: str
    role: str
    is_active: bool
    # Same token as returned by login; lets the frontend recover it after a page reload.
    csrf_token: str
