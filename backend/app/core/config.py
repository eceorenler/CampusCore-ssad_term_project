"""Application settings, loaded from environment variables or a .env file."""

from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # "development" or "production". Production enables Secure cookies and strict checks.
    environment: str = "development"

    # SQLAlchemy URL using the psycopg (v3) driver.
    database_url: str = "postgresql+psycopg://campuscore:campuscore@localhost:5432/campuscore"

    # Base64-encoded 32-byte key for AES-256-GCM encryption of QR tokens.
    # Spec v1.3 section 3: the key must live outside the database.
    qr_encryption_key: str

    # Spec R11: fixed 8-hour absolute session lifetime.
    session_lifetime_hours: int = 8
    # Spec section 7. The "__Host-" prefix requires HTTPS, so in development the prefix
    # is dropped automatically (see session_cookie property) and the demo works on http://localhost.
    session_cookie_base_name: str = "campuscore_session"
    # last_seen_at is refreshed at most this often, to avoid a DB write on every request.
    session_last_seen_update_seconds: int = 300

    # CSRF token travels in this header on POST/PATCH/DELETE (spec section 7).
    csrf_header_name: str = "X-CSRF-Token"

    # Login throttling (spec section 5 and 7): failed attempts per (IP, email) in a window.
    login_max_failures: int = 5
    login_failure_window_seconds: int = 900

    # Business rules (spec R1, R6). Kept here so they are defined in one place.
    max_reservation_minutes: int = 120
    check_in_grace_minutes: int = 15

    # Resource opening hours are local wall-clock times in this zone (spec section 2).
    campus_timezone: str = "Europe/Istanbul"

    # No-show background job (spec section 8). Runs inside the API process.
    run_no_show_job: bool = True
    no_show_job_interval_seconds: int = 60

    # Local development only: frontend origin(s) allowed by CORS. Never "*".
    cors_origins: list[str] = ["http://localhost:5173"]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def campus_tz(self) -> ZoneInfo:
        return ZoneInfo(self.campus_timezone)

    @property
    def session_cookie(self) -> str:
        """__Host-campuscore_session in production (HTTPS), campuscore_session in development."""
        return f"__Host-{self.session_cookie_base_name}" if self.is_production else self.session_cookie_base_name


@lru_cache
def get_settings() -> Settings:
    return Settings()
