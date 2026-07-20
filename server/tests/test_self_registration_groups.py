from datetime import datetime

from app import models
from app.db import SessionLocal
from app.security import hash_token
from tests.test_auth import _mk_teacher


def _teacher(client):
    _mk_teacher()
    assert client.post("/login", json={"username": "admin", "password": "pw123456"}).status_code == 200


def _student_headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_student_self_registration_and_group_lock(client):
    _teacher(client)
    course_id = client.post("/courses", json={"name": "VC", "term": "2026"}).json()["id"]
    invite = client.post(f"/courses/{course_id}/enrollment-code", json={"max_group_size": 2}).json()["enrollment_code"]
    first = client.post("/api/student-registration", json={"course_code": invite, "student_no": "1", "name": "甲"})
    assert first.status_code == 201
    first_token = first.json()["submit_token"]
    second = client.post("/api/student-registration", json={"course_code": invite, "student_no": "2", "name": "乙"})
    assert second.status_code == 201
    assert client.post("/api/student-registration", json={"course_code": invite, "student_no": "1", "name": "甲"}).status_code == 409
    created = client.post("/api/student-groups", headers=_student_headers(first_token), json={"name": "火箭队"})
    assert created.status_code == 200
    joined = client.post("/api/student-groups/join", headers=_student_headers(second.json()["submit_token"]), json={"join_code": created.json()["join_code"]})
    assert joined.status_code == 200 and joined.json()["group"]["name"] == "火箭队"
    assert client.post(f"/courses/{course_id}/group-lock", json={"locked": True}).json()["groups_locked"] is True
    db = SessionLocal()
    assert db.query(models.Student).filter_by(submit_token_hash=hash_token(first_token)).count() == 1
    db.close()


def test_teacher_can_move_before_but_not_after_submission(client):
    _teacher(client)
    course_id = client.post("/courses", json={"name": "VC", "term": ""}).json()["id"]
    invite = client.post(f"/courses/{course_id}/enrollment-code", json={}).json()["enrollment_code"]
    registered = client.post("/api/student-registration", json={"course_code": invite, "student_no": "1", "name": "甲"}).json()
    g1 = client.post(f"/courses/{course_id}/groups", json={"name": "G1"}).json()["id"]
    g2 = client.post(f"/courses/{course_id}/groups", json={"name": "G2"}).json()["id"]
    db = SessionLocal()
    student = db.query(models.Student).filter_by(student_no=registered["student_no"]).one()
    assert client.post(f"/students/{student.id}/group", json={"group_id": g1}).status_code == 200
    assignment = models.Assignment(course_id=course_id, code="ABCDEFGH", title="A", rubric_json=[], opens_at=datetime(2026, 1, 1), deadline=datetime(2026, 12, 31))
    db.add(assignment)
    db.flush()
    db.add(models.Submission(assignment_id=assignment.id, student_id=student.id))
    db.commit()
    db.close()
    assert client.post(f"/students/{student.id}/group", json={"group_id": g2}).status_code == 409
