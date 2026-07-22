from app.db import SessionLocal
from app import models
from tests.test_auth import _mk_teacher


def _login(client):
    _mk_teacher()
    client.post("/login", json={"username": "admin", "password": "pw123456"})


def test_roster_import_creates_students_without_credentials(client):
    _login(client)
    r = client.post("/courses", json={"name": "VC101", "term": "2026秋"})
    cid = r.json()["id"]
    csv_text = "学号,姓名,小组\n2024001,张三,第1组\n2024002,李四,第1组\n2024003,王五,第2组\n"
    r = client.post(f"/courses/{cid}/roster", json={"csv": csv_text})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created_students"] == 3
    db = SessionLocal()
    students = db.query(models.Student).all()
    assert len(students) == 3
    assert db.query(models.Group).count() == 2
    assert all(s.password_hash is None for s in students)
    db.close()


def test_course_creation_generates_one_enrollment_code(client):
    _login(client)
    created = client.post("/courses", json={"name": "VC101", "term": "2026秋"})
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["enrollment_code"].startswith("vc_")

    db = SessionLocal()
    enrollment = db.query(models.CourseEnrollment).filter_by(course_id=body["id"]).one()
    db.close()
    assert enrollment.enrollment_code == body["enrollment_code"]

    repeated = client.post(
        f"/courses/{body['id']}/enrollment-code", json={"max_group_size": 2}
    )
    assert repeated.status_code == 200
    assert repeated.json()["enrollment_code"] == body["enrollment_code"]
    assert repeated.json()["max_group_size"] == 6

    settings = client.put(
        f"/courses/{body['id']}/enrollment-settings", json={"max_group_size": 2}
    )
    assert settings.status_code == 200
    assert settings.json()["enrollment_code"] == body["enrollment_code"]
    assert settings.json()["max_group_size"] == 2

    duplicate = client.post("/courses", json={"name": " VC101 ", "term": "2026秋"})
    assert duplicate.status_code == 409


def test_teacher_cannot_reset_student_password(client):
    _login(client)
    cid = client.post("/courses", json={"name": "C", "term": ""}).json()["id"]
    client.post(f"/courses/{cid}/roster", json={"csv": "学号,姓名,小组\n1,甲,G\n"})
    db = SessionLocal()
    sid = db.query(models.Student).one().id
    db.close()
    assert client.post(f"/students/{sid}/reset-token").status_code == 404


def test_installation_registers_imported_student_with_password(client):
    _login(client)
    cid = client.post("/courses", json={"name": "C", "term": ""}).json()["id"]
    invite = client.post(f"/courses/{cid}/enrollment-code", json={}).json()["enrollment_code"]
    client.post(f"/courses/{cid}/roster", json={"csv": "学号,姓名,小组\n1,甲,G\n"})

    response = client.post(
        "/api/student-registration",
        json={
            "course_code": invite,
            "student_no": "1",
            "name": "甲",
            "password": "student-pass",
            "password_confirm": "student-pass",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["created"] is False
    assert client.get("/api/student/ping", auth=("1", "student-pass")).status_code == 200


def test_roster_requires_teacher(client):
    assert client.post("/courses", json={"name": "C", "term": ""}).status_code == 401
