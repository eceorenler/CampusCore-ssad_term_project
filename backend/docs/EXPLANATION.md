# Backend: what was built and how it works (presentation notes)

## Concepts

- **FastAPI**: the Python framework for the API. It defines the addresses (endpoints) the frontend calls.
- **PostgreSQL**: the database that stores all data.
- **SQLAlchemy (ORM)**: lets us write tables as Python classes (`app/db/models.py`) and query without hand-written SQL.
- **Alembic (migrations)**: manages the files that create and change tables. `alembic upgrade head` builds the schema. Think of it as "git for the database".
- **Docker Compose**: runs PostgreSQL with one command (`docker compose up -d`) without installing it.

## Tables (6)

| Table | What it stores |
| --- | --- |
| users | Users; role STUDENT / STAFF / ADMIN; password hashed with Argon2id |
| user_sessions | Login sessions; only the SHA-256 digest of the token is stored; valid for 8 hours |
| resources | Rooms, labs, equipment; daily opening and closing times |
| reservations | Bookings; status CONFIRMED / CHECKED_IN / CANCELLED / NO_SHOW |
| check_ins | Who checked in, when, and which STAFF member verified it |
| resource_unavailability | Maintenance closures entered by an ADMIN |

## Questions the instructor may ask

**"What happens if two people book the same room at the same moment?"**
The PostgreSQL `no_active_overlap` constraint (a GiST exclusion constraint) does not allow two active reservations of the same resource with overlapping times. Even if both requests arrive in the same millisecond, one succeeds and the other gets an error (409 RESERVATION_CONFLICT in the API). This is tested.

**"Do 10:00-11:00 and 11:00-12:00 overlap?"**
No. Intervals are half-open `[start, end)`: the end moment is not part of the interval.

**"Does a cancelled reservation free its time?"**
Yes. The constraint only looks at CONFIRMED and CHECKED_IN reservations.

**"How is the QR code secure?"**
Each reservation gets a 256-bit random token. The database stores its SHA-256 digest (for lookup) and an AES-GCM encrypted copy (so the owner can see the same QR again). The encryption key is in the `.env` file, not in the database, so a stolen database does not reveal QR codes.

**"How are passwords stored?"**
Hashed with Argon2id; plain text is never stored anywhere.

**"Why can't users be deleted?"**
Booking history must be kept (spec). All foreign keys are `ON DELETE RESTRICT`. A user is deactivated (`is_active = false`) instead of deleted.

**"Why are times stored in UTC?"**
The spec requires it: the database stores UTC and the API answers in Turkish time (+03:00). This avoids time-zone mix-ups.

**"How does login work?"**
After a successful login a random session token is created and given to the browser as an HttpOnly cookie (JavaScript cannot read it). The database only stores its SHA-256 digest. A session is valid for exactly 8 hours; activity does not extend it. Logout revokes the session immediately.

**"What is CSRF and how do you prevent it?"**
CSRF is when another website makes the user's browser send a request to our API using the user's cookie. Login and `/auth/me` return a `csrf_token`; the frontend sends it back in the `X-CSRF-Token` header on every POST/PATCH request. A malicious site cannot know this token. The `Origin` header is checked as well.

**"What about password-guessing attacks?"**
After 5 failed attempts for the same IP + email within 15 minutes, the API returns 429. The error message is always the same ("Invalid email or password"), so it never reveals whether an email is registered.

**"What is checked when a reservation is created?"** (in this order)
1. Is the duration above 0 and at most 120 minutes, and is the start in the future? (400)
2. The resource row is locked (`SELECT ... FOR UPDATE`), so a maintenance closure created at the same moment cannot conflict.
3. Is the resource active? Is the time within opening hours? Does it overlap a maintenance closure? (409)
4. Expired no-shows are marked NO_SHOW right away, so their time can be booked again.
5. The row is inserted; if it overlaps, the GiST constraint rejects it (409 RESERVATION_CONFLICT).

**"How does QR check-in work?"**
Staff scan the QR and select the resource they are at. In order: is the QR valid, does it belong to this resource, is the staff member scanning their own reservation (not allowed), is the status CONFIRMED, is the time between the start and start + 15 minutes (both ends included). The response contains the holder's name so staff can compare it with the student ID card (a screenshot of a QR could have been shared).

**"How does no-show work?"**
A background task runs every 60 seconds and marks reservations that are still CONFIRMED 15 minutes after their start as NO_SHOW. Because the update is conditional (`UPDATE ... WHERE status = 'CONFIRMED'`), it cannot clash with a check-in happening at the same time: whichever comes first wins.

**"What does a maintenance closure do?"**
An admin closes a resource for a time range. In the same transaction, future CONFIRMED reservations that overlap the range (even partially) become CANCELLED (`cancellation_reason = RESOURCE_CLOSURE`). Reservations that have already started or are CHECKED_IN are not changed; they are returned to the admin as a "manual review" list.

**"How did you test this?"**
`tests/test_api.py` covers every acceptance criterion in section 10 of the spec. Tests use a fixed fake clock, so boundaries such as "check-in accepted at exactly minute 15, rejected at 15 minutes and 1 second" are tested exactly. Tests run against a separate database (`campuscore_test`).

## Design patterns (for report section 5.7)

- **Layered architecture**: router (HTTP) → service (business rules) → database. Example: `app/modules/reservations/router.py` → `service.py`.
- **Dependency Injection**: FastAPI `Depends` injects the database session, the logged-in user, role checks and CSRF checks into endpoints (`app/core/dependencies.py`). Endpoints do not create these themselves, and tests can replace them.
- **Shared rules module**: booking rules live in one place (`app/modules/reservations/rules.py`) and are reused by the availability preview, booking creation and closure creation.

## Remaining work

The code is complete. Still to do: run `pytest -v` against a real PostgreSQL database and integrate with the frontend.
