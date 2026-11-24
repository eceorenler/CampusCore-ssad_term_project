# CampusCore Backend

Campus Resource Reservation and QR Check-in System, SWE307 term project.
Implements the **CampusCore Backend Technical Specification v1.3** (see `docs/`).

Stack: Python 3.11+ · FastAPI · PostgreSQL 16 · SQLAlchemy 2 · Alembic · Argon2id · AES-GCM

## Status

| Spec step | Content | Status |
| --- | --- | --- |
| 1 | Database migrations (6 tables, constraints, GiST overlap guard), seed data | Done |
| 2 | Auth: login/logout/me, 8-hour sessions, CSRF, roles, login throttling | Done |
| 3 | Resources, occupied intervals, availability preview | Done |
| 4 | Reservation lifecycle, scheduled closures with automatic cancellation | Done |
| 5 | QR re-display, staff check-in, no-show job | Done |
| 6 | Developer tests (`tests/test_api.py`, `tests/test_schema.py`) | Written |

## Run locally

Requirements: Python 3.11+, Docker (or a local PostgreSQL 16).

```bash
# 1. Start PostgreSQL (also creates the campuscore_test database for pytest)
docker compose up -d

# 2. Python environment
python -m venv .venv
.venv\Scripts\activate               # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

# 3. Configuration
copy .env.example .env               # macOS/Linux: cp .env.example .env
python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"
#   -> paste the output as QR_ENCRYPTION_KEY in .env

# 4. Create tables and demo data
alembic upgrade head
python -m app.scripts.seed

# 5. Start the API
uvicorn app.main:app --reload
```

- Health check: http://localhost:8000/api/v1/health
- API docs (Swagger): http://localhost:8000/api/v1/docs

Demo accounts (password `Campus123!`): `student@campus.test`, `student2@campus.test`,
`staff@campus.test`, `staff2@campus.test`, `admin@campus.test`.

## Tests

```bash
pytest -v
```

Tests use the separate `campuscore_test` database and wipe it before each API test; they refuse to run
against a database whose name does not end in `_test`. If your PostgreSQL container was created before
`docker/init-test-db.sql` existed, create the database once:

```bash
docker compose exec db createdb -U campuscore campuscore_test
```

`tests/test_api.py` covers the spec section 10 acceptance criteria with a fixed test clock: concurrent
bookings (exactly one wins), touching bookings, 2-hour limit, inactive resource, opening hours, closures,
privacy (404 for other users' bookings, no owner data in the calendar), check-in window boundaries,
duplicate scans, self-verification, no-show job and check-in race, QR re-display, CSRF, logout, 8-hour
expiry, ADMIN cannot book, usage counts, the admin user list and role changes.

## Endpoints (all under `/api/v1`)

| Method | Path | Access |
| --- | --- | --- |
| POST | `/auth/login` | Public |
| POST | `/auth/logout` | Logged in, CSRF |
| GET | `/auth/me` | Logged in |
| GET | `/resources`, `/resources/{id}` | Logged in |
| GET | `/resources/{id}/occupied?date=&timezone=` | Logged in |
| GET | `/resources/{id}/availability?start_time=&end_time=` | Logged in |
| POST | `/reservations` | STUDENT / STAFF, CSRF |
| GET | `/reservations` | STUDENT / STAFF (own) |
| GET | `/reservations/{id}` | Owner / ADMIN |
| POST | `/reservations/{id}/cancel` | Owner, CSRF |
| GET | `/reservations/{id}/qr` | Owner |
| POST | `/check-ins/verify` | STAFF, CSRF |
| POST | `/admin/resources` | ADMIN, CSRF |
| PATCH | `/admin/resources/{id}` | ADMIN, CSRF |
| POST | `/admin/resources/{id}/deactivate` | ADMIN, CSRF |
| GET / POST | `/admin/resources/{id}/unavailability` | ADMIN (POST: CSRF) |
| GET | `/admin/reservations` | ADMIN |
| GET | `/admin/usage` | ADMIN |
| GET | `/admin/users?search=&role=` | ADMIN |
| PATCH | `/admin/users/{id}/role` | ADMIN, CSRF |
| GET | `/health` | Public |

## Notes for the frontend developer

- Send requests with credentials (`fetch(url, { credentials: "include" })`); the session is an HttpOnly cookie.
- `POST /auth/login` and `GET /auth/me` return `csrf_token`. Send it as the `X-CSRF-Token` header on every
  POST/PATCH request. After a page reload, call `/auth/me` to get it again.
- Times: send ISO 8601 with offset (`2026-11-20T10:00:00+03:00`); responses use the +03:00 campus offset.
- Errors are always `{"error": {"code": "...", "message": "..."}}`; use `code` for logic, `message` for display.
- Swagger: log in with `/auth/login`, copy `csrf_token`, click **Authorize** and paste it into `X-CSRF-Token`.

## Implementation choices not spelled out in spec v1.3 (for System Architect review)

| Topic | Choice |
| --- | --- |
| CSRF token delivery | `csrf_token` field in login and `/auth/me` responses; token = SHA-256 of the session token, so it is bound to the session without an extra column |
| Session cookie in development | `campuscore_session` without `Secure` over http://localhost; production uses `__Host-campuscore_session` with `Secure` |
| Registration | No self-registration endpoint (not in spec); accounts come from the seed script, roles via `PATCH /admin/users/{id}/role` |
| Admin user list | `GET /admin/users` added (approved by System Architect) so the admin can find a user to change roles; entry for the spec in `docs/spec-v1.4-admin-users.md` |
| Missed check-in | A CONFIRMED booking past start + 15 min no longer blocks its slot; booking creation and closure creation mark such rows NO_SHOW immediately, the job does the rest every 60 s |
| QR after the grace period | Rejected with 409 `CHECK_IN_WINDOW_CLOSED` and the reservation is marked NO_SHOW at once |
| Extra error codes | 400 `START_TIME_IN_PAST`, 400 `INVALID_INTERVAL` (closure), 409 `LAST_ADMIN` |
| Wrong resource at check-in | 400 `INVALID_QR` (decision table 2: "invalid QR or details") |
| QR at non-CONFIRMED reservation | 409 `INVALID_STATUS` |
| Extra response fields | `cancellation_reason` in reservation lists/detail; `holder_name` in check-in response so staff can compare with the student ID; `opens_at`/`closes_at` in resource detail and occupied response |
| ADMIN resource listing | ADMIN sees inactive resources too; ordinary users get 404 for inactive ones |
| Login throttling | 5 failed attempts per (IP, email) in 15 minutes -> 429; kept in memory (one API process) |
| Audit | Role changes and closures are written to the `campuscore.audit` log (no audit table in spec) |
| No-show job | Background thread in the API process; a PostgreSQL advisory lock keeps it single-run with several workers |

## Project structure

```
app/
  main.py               FastAPI app, routers, security headers, no-show worker
  core/
    config.py           Settings from .env (business rule values live here)
    clock.py            utcnow(), replaced by a fake clock in tests
    api_types.py        +03:00 date-time output, pagination
    dependencies.py     current user, role checks, CSRF
    errors.py           {"error": {"code", "message"}} envelope for all errors
    security.py         Argon2id, random tokens, SHA-256, CSRF token, AES-GCM QR encryption
  db/                   engine, models (6 tables), constraint-error helper
  modules/
    auth/               login, logout, me, rate limiter
    resources/          catalogue, occupied, availability
    reservations/       create, list, detail, cancel, QR; rules.py = shared booking rules
    check_ins/          staff QR verification
    admin/              resources, closures, reservations, usage, roles
  jobs/no_show.py       no-show worker (also: python -m app.jobs.no_show)
  scripts/seed.py       demo users and resources
migrations/versions/    Alembic migrations (0001 = initial schema)
tests/                  conftest.py (test DB, fake clock), test_api.py, test_schema.py
docker/                 init-test-db.sql
```

## Database rules enforced by PostgreSQL

| Rule (spec) | Constraint |
| --- | --- |
| R3 no overlapping active bookings, incl. concurrent requests | `no_active_overlap` (GiST exclusion, half-open ranges) |
| R1 end after start, max 120 minutes | `ck_reservations_time_order`, `ck_reservations_max_duration` |
| Unique case-insensitive email | `uq_users_email_lower` |
| One check-in per reservation | `uq_check_ins_reservation_id` |
| Unique QR per reservation (R5) | `uq_reservations_qr_token_hash` |
| Valid roles / statuses | `ck_users_role`, `ck_reservations_status` |
| History is never deleted | all foreign keys `ON DELETE RESTRICT` |

Rules that need the current time or other tables (future start, opening hours, closures, cancellation
window, check-in window, ADMIN cannot book, STAFF cannot self-verify) are enforced in the service layer.
Booking and closure creation lock the resource row (`SELECT ... FOR UPDATE`) so they cannot race.
