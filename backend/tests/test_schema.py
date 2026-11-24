"""Database-level rule tests. Run against a migrated database:

    alembic upgrade head
    pytest tests/test_schema.py -v

Each test runs inside a transaction that is rolled back, so the database is left unchanged.
"""

import threading
import time

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.session import engine

INSERT_RES = text(
    "INSERT INTO reservations (user_id, resource_id, start_time, end_time, qr_token_hash, qr_token_ciphertext) "
    "VALUES (:u, :r, :s, :e, :h, 'ciphertext')"
)


@pytest.fixture
def conn():
    with engine.connect() as c:
        tx = c.begin()
        user_id = c.execute(text(
            "INSERT INTO users (full_name, email, password_hash, role) "
            "VALUES ('Test', 'pytest-user@campus.test', 'x', 'STUDENT') RETURNING id"
        )).scalar_one()
        resource_id = c.execute(text(
            "INSERT INTO resources (name, type, opens_at, closes_at) "
            "VALUES ('Pytest Room', 'STUDY_ROOM', '08:00', '22:00') RETURNING id"
        )).scalar_one()
        c.info.update(user_id=user_id, resource_id=resource_id)
        yield c
        tx.rollback()


def book(c, start, end, h):
    c.execute(INSERT_RES, dict(u=c.info["user_id"], r=c.info["resource_id"], s=start, e=end, h=h * 64))


def expect_violation(c, constraint, fn):
    sp = c.begin_nested()
    with pytest.raises(IntegrityError) as exc:
        fn()
    sp.rollback()
    assert constraint in str(exc.value)


def test_overlap_rejected(conn):
    book(conn, "2030-01-10 10:00+03", "2030-01-10 11:00+03", "a")
    expect_violation(conn, "no_active_overlap",
                     lambda: book(conn, "2030-01-10 10:30+03", "2030-01-10 11:30+03", "b"))


def test_touching_bookings_allowed(conn):
    book(conn, "2030-01-10 10:00+03", "2030-01-10 11:00+03", "a")
    book(conn, "2030-01-10 11:00+03", "2030-01-10 12:00+03", "b")  # half-open [start, end)


def test_cancelled_booking_frees_slot(conn):
    book(conn, "2030-01-10 10:00+03", "2030-01-10 11:00+03", "a")
    conn.execute(text("UPDATE reservations SET status = 'CANCELLED' WHERE qr_token_hash = :h"), dict(h="a" * 64))
    book(conn, "2030-01-10 10:00+03", "2030-01-10 11:00+03", "b")


def test_max_duration_120_minutes(conn):
    book(conn, "2030-01-10 08:00+03", "2030-01-10 10:00+03", "a")  # exactly 120 min is fine
    expect_violation(conn, "ck_reservations_max_duration",
                     lambda: book(conn, "2030-01-11 08:00+03", "2030-01-11 10:01+03", "b"))


def test_end_must_be_after_start(conn):
    expect_violation(conn, "ck_reservations_time_order",
                     lambda: book(conn, "2030-01-10 10:00+03", "2030-01-10 09:00+03", "a"))


def test_email_unique_case_insensitive(conn):
    expect_violation(conn, "uq_users_email_lower", lambda: conn.execute(text(
        "INSERT INTO users (full_name, email, password_hash, role) "
        "VALUES ('Dup', 'PYTEST-USER@campus.test', 'x', 'STUDENT')"
    )))


def test_one_check_in_per_reservation(conn):
    book(conn, "2030-01-10 10:00+03", "2030-01-10 11:00+03", "a")
    rid = conn.execute(text("SELECT id FROM reservations WHERE qr_token_hash = :h"), dict(h="a" * 64)).scalar_one()
    insert = text("INSERT INTO check_ins (reservation_id, verified_by, checked_in_at) VALUES (:r, :u, now())")
    conn.execute(insert, dict(r=rid, u=conn.info["user_id"]))
    expect_violation(conn, "uq_check_ins_reservation_id",
                     lambda: conn.execute(insert, dict(r=rid, u=conn.info["user_id"])))


def test_concurrent_overlapping_bookings_only_one_wins():
    """Spec section 10, first acceptance test: two users book the same slot at the same moment."""
    with engine.begin() as c:
        uid = c.execute(text(
            "INSERT INTO users (full_name, email, password_hash, role) "
            "VALUES ('Race', 'pytest-race@campus.test', 'x', 'STUDENT') RETURNING id"
        )).scalar_one()
        rid = c.execute(text(
            "INSERT INTO resources (name, type, opens_at, closes_at) "
            "VALUES ('Race Room', 'STUDY_ROOM', '08:00', '22:00') RETURNING id"
        )).scalar_one()

    results = []

    def attempt(tag):
        try:
            with engine.begin() as c:
                c.execute(INSERT_RES, dict(u=uid, r=rid, s="2030-02-01 14:00+03", e="2030-02-01 15:00+03",
                                           h=tag * 64))
                time.sleep(0.5)  # hold the transaction open so both overlap in time
            results.append("ok")
        except IntegrityError:
            results.append("conflict")

    try:
        threads = [threading.Thread(target=attempt, args=(t,)) for t in ("x", "y")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert sorted(results) == ["conflict", "ok"]
    finally:
        with engine.begin() as c:
            c.execute(text("DELETE FROM reservations WHERE resource_id = :r"), dict(r=rid))
            c.execute(text("DELETE FROM resources WHERE id = :r"), dict(r=rid))
            c.execute(text("DELETE FROM users WHERE id = :u"), dict(u=uid))
