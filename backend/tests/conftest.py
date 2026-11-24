"""Test setup. Tests run against a separate PostgreSQL database (campuscore_test) that is
wiped before every API test, so the development database and its seed data are never touched.

    docker compose up -d          # also creates campuscore_test (docker/init-test-db.sql)
    pytest -v
"""

import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Must be set before any app module is imported (settings are read once).
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://campuscore:campuscore@localhost:5432/campuscore_test"
)
os.environ.setdefault("QR_ENCRYPTION_KEY", "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")  # test-only key
os.environ["RUN_NO_SHOW_JOB"] = "false"  # tests call the job directly
os.environ["ENVIRONMENT"] = "development"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.core import clock  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.auth.rate_limit import login_rate_limiter  # noqa: E402

IST = ZoneInfo("Europe/Istanbul")
PASSWORD = "Campus123!"
USERS = {
    "student": ("Test Student", "STUDENT"),
    "student2": ("Test Student 2", "STUDENT"),
    "staff": ("Test Staff", "STAFF"),
    "staff2": ("Test Staff 2", "STAFF"),
    "admin": ("Test Admin", "ADMIN"),
}


def local(hh: int, mm: int = 0, day: int = 10) -> datetime:
    """A time on 2030-01-<day> in Europe/Istanbul (the fixed test date)."""
    return datetime(2030, 1, day, hh, mm, tzinfo=IST)


def iso(dt: datetime) -> str:
    return dt.isoformat()


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    db_name = make_url(os.environ["DATABASE_URL"]).database or ""
    if not db_name.endswith("_test"):
        pytest.exit(f"Refusing to run tests against '{db_name}': database name must end with _test.")
    command.upgrade(Config("alembic.ini"), "head")


class FakeClock:
    def __init__(self, start: datetime):
        self.now = start

    def set(self, dt: datetime) -> None:
        self.now = dt

    def advance(self, **kwargs) -> None:
        self.now += timedelta(**kwargs)


@pytest.fixture
def fake_clock(monkeypatch):
    c = FakeClock(local(8, 0))
    monkeypatch.setattr(clock, "utcnow", lambda: c.now)
    return c


@pytest.fixture
def db_data(fake_clock):
    """Empty tables, then five users (one per demo role) and one resource open 08:00-22:00."""
    login_rate_limiter.clear()
    password_hash = hash_password(PASSWORD)
    with engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE check_ins, reservations, resource_unavailability, user_sessions, resources, users "
            "RESTART IDENTITY CASCADE"
        ))
        ids = {}
        for key, (name, role) in USERS.items():
            ids[key] = conn.execute(text(
                "INSERT INTO users (full_name, email, password_hash, role) VALUES (:n, :e, :p, :r) RETURNING id"
            ), dict(n=name, e=f"{key}@campus.test", p=password_hash, r=role)).scalar_one()
        ids["room"] = conn.execute(text(
            "INSERT INTO resources (name, type, location, capacity, opens_at, closes_at) "
            "VALUES ('Study Room A', 'STUDY_ROOM', 'Library', 6, '08:00', '22:00') RETURNING id"
        )).scalar_one()
    return ids


class ApiClient:
    """A TestClient logged in as one user, sending the CSRF header automatically."""

    def __init__(self, email: str):
        self.http = TestClient(app)
        r = self.http.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        assert r.status_code == 200, r.text
        self.user = r.json()
        self.csrf = self.user["csrf_token"]

    def get(self, path, **kw):
        return self.http.get(f"/api/v1{path}", **kw)

    def _write(self, method, path, csrf=True, **kw):
        headers = kw.pop("headers", {})
        if csrf:
            headers["X-CSRF-Token"] = self.csrf
        return self.http.request(method, f"/api/v1{path}", headers=headers, **kw)

    def post(self, path, csrf=True, **kw):
        return self._write("POST", path, csrf, **kw)

    def patch(self, path, csrf=True, **kw):
        return self._write("PATCH", path, csrf, **kw)


@pytest.fixture
def login(db_data):
    """login("student") -> ApiClient for student@campus.test."""
    return lambda key: ApiClient(f"{key}@campus.test")
