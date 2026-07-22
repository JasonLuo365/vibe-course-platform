from app import models
from app.db import SessionLocal
from app.security import hash_password


def _mk_student():
    db = SessionLocal()
    course = models.Course(name="C", term="")
    db.add(course)
    db.flush()
    student = models.Student(
        course_id=course.id, student_no="1", name="甲", password_hash=hash_password("student-pass")
    )
    db.add(student)
    db.commit()
    db.close()


def test_basic_auth(client):
    _mk_student()
    assert client.get("/api/student/ping").status_code == 401
    assert client.get("/api/student/ping", auth=("1", "wrong-password")).status_code == 401
    r = client.get("/api/student/ping", auth=("1", "student-pass"))
    assert r.status_code == 200 and r.json()["student_no"] == "1"


def test_rate_limit(client, settings):
    _mk_student()
    n = settings.rate_limit_per_minute
    for _ in range(n):
        assert client.get("/api/student/ping", auth=("1", "student-pass")).status_code == 200
    assert client.get("/api/student/ping", auth=("1", "student-pass")).status_code == 429


def test_rate_limit_uses_forwarded_ip_only_when_enabled(client, settings):
    settings.trust_proxy_headers = True
    settings.rate_limit_per_minute = 1
    _mk_student()
    assert client.get("/api/student/ping", auth=("1", "student-pass"), headers={"X-Forwarded-For": "203.0.113.10"}).status_code == 200
    assert client.get("/api/student/ping", auth=("1", "student-pass"), headers={"X-Forwarded-For": "203.0.113.11"}).status_code == 200


def test_student_login_and_password_reset(client):
    _mk_student()
    assert client.post("/student/login", json={"student_no": "1", "password": "student-pass"}).status_code == 200
    assert client.post(
        "/student/password/reset",
        json={"student_no": "1", "password": "new-password", "password_confirm": "different"},
    ).status_code == 422
    assert client.post(
        "/student/password/reset",
        json={"student_no": "1", "password": "new-password", "password_confirm": "new-password"},
    ).json() == {"ok": True}
    assert client.post("/student/login", json={"student_no": "1", "password": "student-pass"}).status_code == 401
    assert client.post("/student/login", json={"student_no": "1", "password": "new-password"}).status_code == 200


def test_student_password_rejects_more_than_12_characters(client):
    _mk_student()
    too_long = "student-password"
    response = client.post(
        "/student/password/reset",
        json={"student_no": "1", "password": too_long, "password_confirm": too_long},
    )
    assert response.status_code == 422


def test_password_reset_uses_a_dedicated_page(client):
    login_page = client.get("/login")
    assert 'href="/student/password/reset"' in login_page.text
    assert 'student-password-reset-form' not in login_page.text

    reset_page = client.get("/student/password/reset")
    assert reset_page.status_code == 200
    assert 'student-password-reset-form' in reset_page.text
    assert 'type="text" id="reset-password" minlength="8" maxlength="12"' in reset_page.text
    assert '密码要求为 8–12 位' in reset_page.text
    assert 'href="/login"' in reset_page.text
