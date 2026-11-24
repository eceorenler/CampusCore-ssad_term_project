"""API tests mapped to spec v1.3 section 10 (backend acceptance criteria).

The clock is fixed at 2030-01-10 08:00 Europe/Istanbul (see conftest.FakeClock), so
time-dependent rules (future start, 15-minute check-in window, no-show, 8-hour session)
are tested deterministically.
"""

import threading

from fastapi.testclient import TestClient

from app.jobs.no_show import run_once as run_no_show_job
from app.main import app
from tests.conftest import PASSWORD, iso, local


def book(client, resource_id, start, end):
    return client.post("/reservations", json={"resource_id": resource_id, "start_time": iso(start), "end_time": iso(end)})


def qr_of(client, reservation_id):
    r = client.get(f"/reservations/{reservation_id}/qr")
    assert r.status_code == 200, r.text
    return r.json()["qr_payload"]


def verify(staff, token, resource_id):
    return staff.post("/check-ins/verify", json={"qr_token": token, "resource_id": resource_id})


def error_code(response):
    return response.json()["error"]["code"]


# ---------- auth and sessions ----------

def test_login_me_and_generic_failure(login, db_data):
    student = login("student")
    me = student.get("/auth/me").json()
    assert me["email"] == "student@campus.test" and me["role"] == "STUDENT"
    assert me["csrf_token"] == student.csrf

    anon = TestClient(app)
    wrong_pw = anon.post("/api/v1/auth/login", json={"email": "student@campus.test", "password": "nope"})
    unknown = anon.post("/api/v1/auth/login", json={"email": "ghost@campus.test", "password": "nope"})
    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.json() == unknown.json()  # does not reveal whether the email exists


def test_login_is_rate_limited(db_data):
    anon = TestClient(app)
    for _ in range(5):
        assert anon.post("/api/v1/auth/login", json={"email": "student@campus.test", "password": "x"}).status_code == 401
    r = anon.post("/api/v1/auth/login", json={"email": "student@campus.test", "password": PASSWORD})
    assert r.status_code == 429 and error_code(r) == "RATE_LIMITED"


def test_logout_then_protected_request_is_401(login):
    student = login("student")
    assert student.post("/auth/logout", csrf=False).status_code == 403  # CSRF required
    assert student.post("/auth/logout").status_code == 204
    assert student.get("/auth/me").status_code == 401


def test_session_expires_after_exactly_8_hours(login, fake_clock):
    student = login("student")
    fake_clock.advance(hours=7, minutes=59)
    assert student.get("/auth/me").status_code == 200  # activity does not extend the session
    fake_clock.advance(minutes=1)
    assert student.get("/auth/me").status_code == 401


def test_missing_csrf_on_state_change_is_403(login, db_data):
    student = login("student")
    r = student.post("/reservations", csrf=False,
                     json={"resource_id": db_data["room"], "start_time": iso(local(10)), "end_time": iso(local(11))})
    assert r.status_code == 403 and error_code(r) == "CSRF_FAILED"


def test_cross_site_origin_is_rejected(login, db_data):
    student = login("student")
    r = student.post("/reservations", headers={"Origin": "https://evil.example"},
                     json={"resource_id": db_data["room"], "start_time": iso(local(10)), "end_time": iso(local(11))})
    assert r.status_code == 403 and error_code(r) == "CSRF_FAILED"


# ---------- booking rules ----------

def test_booking_rules(login, db_data):
    student = login("student")
    room = db_data["room"]

    r = book(student, room, local(10), local(11))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "CONFIRMED" and body["qr_available"] is True
    assert body["start_time"] == "2030-01-10T10:00:00+03:00"

    assert error_code(book(student, room, local(10, 30), local(11, 30))) == "RESERVATION_CONFLICT"
    assert book(student, room, local(11), local(12)).status_code == 201  # touching end/start is allowed
    assert error_code(book(student, room, local(13), local(15, 1))) == "INVALID_DURATION"  # > 2 hours
    assert error_code(book(student, room, local(13), local(13))) == "INVALID_DURATION"
    assert error_code(book(student, room, local(7), local(7, 30))) == "START_TIME_IN_PAST"
    assert error_code(book(student, room, local(21, 30), local(22, 30))) == "OUTSIDE_OPENING_HOURS"
    assert book(student, room, local(20), local(22)).status_code == 201  # ends exactly at closing time


def test_admin_cannot_book_and_inactive_resource_rejected(login, db_data):
    admin, student = login("admin"), login("student")
    r = book(admin, db_data["room"], local(10), local(11))
    assert r.status_code == 403 and error_code(r) == "FORBIDDEN"

    assert admin.post(f"/admin/resources/{db_data['room']}/deactivate").json()["is_active"] is False
    r = book(student, db_data["room"], local(10), local(11))
    assert r.status_code == 409 and error_code(r) == "RESOURCE_INACTIVE"
    assert student.get(f"/resources/{db_data['room']}").status_code == 404  # hidden from ordinary users


def test_concurrent_overlapping_bookings_exactly_one_wins(login, db_data):
    clients = [login("student"), login("student2")]
    results = []

    def attempt(c):
        results.append(book(c, db_data["room"], local(14), local(15)).status_code)

    threads = [threading.Thread(target=attempt, args=(c,)) for c in clients]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [201, 409]


def test_student_cannot_see_other_students_booking(login, db_data):
    owner, other = login("student"), login("student2")
    rid = book(owner, db_data["room"], local(10), local(11)).json()["id"]
    assert other.get(f"/reservations/{rid}").status_code == 404
    assert other.get(f"/reservations/{rid}/qr").status_code == 404
    assert other.post(f"/reservations/{rid}/cancel").status_code == 404
    assert owner.get(f"/reservations/{rid}").json()["user_id"] == owner.user["id"]


def test_cancel_rules(login, db_data, fake_clock):
    student = login("student")
    rid = book(student, db_data["room"], local(10), local(11)).json()["id"]
    r = student.post(f"/reservations/{rid}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "CANCELLED"
    assert error_code(student.post(f"/reservations/{rid}/cancel")) == "INVALID_STATUS"
    assert book(student, db_data["room"], local(10), local(11)).status_code == 201  # slot freed

    rid2 = book(student, db_data["room"], local(12), local(13)).json()["id"]
    fake_clock.set(local(12))
    assert error_code(student.post(f"/reservations/{rid2}/cancel")) == "CANCELLATION_WINDOW_CLOSED"


def test_my_reservations_list(login, db_data):
    student = login("student")
    book(student, db_data["room"], local(10), local(11))
    book(student, db_data["room"], local(12), local(13))
    page = student.get("/reservations?page=1&page_size=20").json()
    assert page["total"] == 2 and page["page"] == 1 and page["page_size"] == 20
    assert page["items"][0]["start_time"] > page["items"][1]["start_time"]  # newest first


# ---------- calendar and availability ----------

def test_occupied_has_no_owner_information(login, db_data):
    student, other = login("student"), login("student2")
    book(student, db_data["room"], local(10), local(11))
    r = other.get(f"/resources/{db_data['room']}/occupied?date=2030-01-10&timezone=Europe/Istanbul")
    assert r.status_code == 200
    body = r.json()
    assert body["opens_at"] == "08:00:00" and body["closes_at"] == "22:00:00"
    assert body["occupied_intervals"] == [
        {"type": "RESERVATION", "start_time": "2030-01-10T10:00:00+03:00", "end_time": "2030-01-10T11:00:00+03:00"}
    ]


def test_availability_preview(login, db_data):
    student = login("student")
    book(student, db_data["room"], local(10), local(11))
    params = {"start_time": iso(local(10, 30)), "end_time": iso(local(11, 30))}
    r = student.get(f"/resources/{db_data['room']}/availability", params=params).json()
    assert r == {"resource_id": db_data["room"], "available": False, "reason": "RESERVATION_CONFLICT"}
    params = {"start_time": iso(local(11)), "end_time": iso(local(12))}
    assert student.get(f"/resources/{db_data['room']}/availability", params=params).json()["available"] is True


# ---------- QR check-in ----------

def test_qr_redisplay_returns_same_token(login, db_data):
    student = login("student")
    rid = book(student, db_data["room"], local(10), local(11)).json()["id"]
    assert qr_of(student, rid) == qr_of(student, rid)
    assert student.get(f"/reservations/{rid}").json().get("qr_payload") is None  # not in detail response


def test_check_in_window_and_duplicates(login, db_data, fake_clock):
    student, staff = login("student"), login("staff")
    rid = book(student, db_data["room"], local(10), local(11)).json()["id"]
    token = qr_of(student, rid)

    fake_clock.set(local(9, 59))
    assert error_code(verify(staff, token, db_data["room"])) == "CHECK_IN_WINDOW_CLOSED"  # before start

    fake_clock.set(local(10, 15))  # start + 15 min is still allowed (inclusive)
    r = verify(staff, token, db_data["room"])
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "CHECKED_IN" and r.json()["holder_name"] == "Test Student"

    r = verify(staff, token, db_data["room"])  # repeated scan
    assert r.status_code == 409 and error_code(r) == "INVALID_STATUS"


def test_qr_after_grace_is_rejected_and_becomes_no_show(login, db_data, fake_clock):
    student, staff = login("student"), login("staff")
    rid = book(student, db_data["room"], local(10), local(11)).json()["id"]
    token = qr_of(student, rid)
    fake_clock.set(local(10, 15))
    fake_clock.advance(seconds=1)  # one second after the inclusive grace boundary
    assert error_code(verify(staff, token, db_data["room"])) == "CHECK_IN_WINDOW_CLOSED"
    assert student.get(f"/reservations/{rid}").json()["status"] == "NO_SHOW"


def test_invalid_qr_wrong_resource_and_role_checks(login, db_data, fake_clock):
    student, staff, admin = login("student"), login("staff"), login("admin")
    other_room = admin.post("/admin/resources", json={
        "name": "Lab 1", "type": "LAB", "opens_at": "08:00:00", "closes_at": "22:00:00"}).json()["id"]
    rid = book(student, db_data["room"], local(10), local(11)).json()["id"]
    token = qr_of(student, rid)
    fake_clock.set(local(10, 5))

    assert error_code(verify(staff, "not-a-real-token", db_data["room"])) == "INVALID_QR"
    assert error_code(verify(staff, token, other_room)) == "INVALID_QR"
    r = verify(student, token, db_data["room"])  # student calls staff check-in
    assert r.status_code == 403 and error_code(r) == "FORBIDDEN"


def test_staff_cannot_verify_own_reservation(login, db_data, fake_clock):
    staff, staff2 = login("staff"), login("staff2")
    rid = book(staff, db_data["room"], local(10), local(11)).json()["id"]
    token = qr_of(staff, rid)
    fake_clock.set(local(10, 1))
    r = verify(staff, token, db_data["room"])
    assert r.status_code == 409 and error_code(r) == "SELF_CHECK_IN_FORBIDDEN"
    assert verify(staff2, token, db_data["room"]).status_code == 200  # another staff member can


# ---------- no-show ----------

def test_no_show_job_releases_slot(login, db_data, fake_clock):
    student, student2 = login("student"), login("student2")
    rid = book(student, db_data["room"], local(10), local(12)).json()["id"]

    fake_clock.set(local(10, 15))
    assert run_no_show_job() == []  # grace period not over yet
    fake_clock.set(local(10, 16))
    assert run_no_show_job() == [rid]
    assert student.get(f"/reservations/{rid}").json()["status"] == "NO_SHOW"
    assert book(student2, db_data["room"], local(10, 30), local(11, 30)).status_code == 201


def test_missed_check_in_releases_slot_even_before_job_runs(login, db_data, fake_clock):
    student, student2 = login("student"), login("student2")
    rid = book(student, db_data["room"], local(10), local(12)).json()["id"]
    fake_clock.set(local(10, 20))  # job has not run
    assert book(student2, db_data["room"], local(10, 30), local(11, 30)).status_code == 201
    assert student.get(f"/reservations/{rid}").json()["status"] == "NO_SHOW"


def test_no_show_job_does_not_touch_checked_in(login, db_data, fake_clock):
    student, staff = login("student"), login("staff")
    rid = book(student, db_data["room"], local(10), local(11)).json()["id"]
    token = qr_of(student, rid)
    fake_clock.set(local(10, 5))
    verify(staff, token, db_data["room"])
    fake_clock.set(local(10, 30))
    assert run_no_show_job() == []
    assert student.get(f"/reservations/{rid}").json()["status"] == "CHECKED_IN"


# ---------- admin: closures, usage, roles ----------

def test_closure_cancels_only_overlapping_future_confirmed(login, db_data, fake_clock):
    student, staff, admin = login("student"), login("staff"), login("admin")
    room = db_data["room"]
    ongoing = book(student, room, local(9), local(11)).json()["id"]
    inside = book(student, room, local(12), local(13)).json()["id"]
    partial = book(student, room, local(15, 30), local(16, 30)).json()["id"]  # overlaps the closure's end
    outside = book(student, room, local(17), local(18)).json()["id"]

    fake_clock.set(local(9, 5))
    assert verify(staff, qr_of(student, ongoing), room).status_code == 200

    r = admin.post(f"/admin/resources/{room}/unavailability",
                   json={"starts_at": iso(local(10)), "ends_at": iso(local(16)), "reason": "Maintenance"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert sorted(body["cancelled_reservation_ids"]) == sorted([partial, inside])
    assert body["requires_manual_review_ids"] == [ongoing]

    assert student.get(f"/reservations/{partial}").json()["cancellation_reason"] == "RESOURCE_CLOSURE"
    assert student.get(f"/reservations/{outside}").json()["status"] == "CONFIRMED"
    assert student.get(f"/reservations/{ongoing}").json()["status"] == "CHECKED_IN"

    r = book(student, room, local(15), local(16))
    assert r.status_code == 409 and error_code(r) == "RESOURCE_CLOSED"

    closures = admin.get(f"/admin/resources/{room}/unavailability").json()["items"]
    assert len(closures) == 1 and closures[0]["reason"] == "Maintenance"
    occupied = student.get(f"/resources/{room}/occupied?date=2030-01-10").json()["occupied_intervals"]
    assert {"RESOURCE_CLOSURE", "RESERVATION"} == {i["type"] for i in occupied}


def test_admin_endpoints_are_admin_only(login, db_data):
    student = login("student")
    assert student.get("/admin/usage").status_code == 403
    assert student.post("/admin/resources", json={
        "name": "X", "type": "LAB", "opens_at": "08:00:00", "closes_at": "09:00:00"}).status_code == 403


def test_resource_create_update_and_hours_validation(login, db_data):
    admin = login("admin")
    r = admin.post("/admin/resources", json={
        "name": "Room B", "type": "STUDY_ROOM", "capacity": 4, "opens_at": "08:00:00", "closes_at": "22:00:00"})
    assert r.status_code == 201 and r.json()["is_active"] is True
    rid = r.json()["id"]
    assert admin.patch(f"/admin/resources/{rid}", json={"capacity": 5}).json()["capacity"] == 5
    bad = admin.patch(f"/admin/resources/{rid}", json={"opens_at": "23:00:00"})
    assert bad.status_code == 422 and error_code(bad) == "VALIDATION_ERROR"
    assert admin.post("/admin/resources", json={
        "name": "Bad", "type": "LAB", "opens_at": "10:00:00", "closes_at": "09:00:00"}).status_code == 422


def test_usage_returns_only_five_counts(login, db_data):
    student, admin = login("student"), login("admin")
    rid = book(student, db_data["room"], local(10), local(11)).json()["id"]
    student.post(f"/reservations/{rid}/cancel")
    book(student, db_data["room"], local(12), local(13))
    assert admin.get("/admin/usage").json() == {
        "total_reservations": 2, "checked_in": 0, "cancelled": 1, "no_show": 0, "total_resources": 1}


def test_admin_user_list(login, db_data):
    admin, student = login("admin"), login("student")
    page = admin.get("/admin/users").json()
    assert page["total"] == 5 and page["page"] == 1 and page["page_size"] == 20
    assert {u["email"] for u in page["items"]} == {f"{k}@campus.test" for k in
                                                   ("student", "student2", "staff", "staff2", "admin")}
    first = page["items"][0]
    assert set(first) == {"id", "full_name", "email", "role", "is_active", "created_at"}  # no password hash

    staff = admin.get("/admin/users?role=STAFF").json()
    assert staff["total"] == 2 and {u["role"] for u in staff["items"]} == {"STAFF"}

    found = admin.get("/admin/users?search=STUDENT 2").json()  # case-insensitive, name or email
    assert [u["email"] for u in found["items"]] == ["student2@campus.test"]
    assert admin.get("/admin/users?search=%25").json()["total"] == 0  # "%" is literal, not a wildcard

    assert len(admin.get("/admin/users?page_size=2").json()["items"]) == 2
    r = student.get("/admin/users")
    assert r.status_code == 403 and error_code(r) == "FORBIDDEN"


def test_role_change_revokes_sessions_and_protects_last_admin(login, db_data):
    admin, student = login("admin"), login("student")
    r = admin.patch(f"/admin/users/{db_data['student']}/role", json={"role": "STAFF"})
    assert r.status_code == 200 and r.json() == {"id": db_data["student"], "role": "STAFF"}
    assert student.get("/auth/me").status_code == 401  # old session revoked

    r = admin.patch(f"/admin/users/{db_data['admin']}/role", json={"role": "STUDENT"})
    assert r.status_code == 409 and error_code(r) == "LAST_ADMIN"
