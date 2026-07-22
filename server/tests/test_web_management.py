from datetime import datetime

from app.db import SessionLocal
from app import models
from tests.test_auth import _mk_teacher


def _login(client):
    _mk_teacher()
    response = client.post("/login", json={"username": "admin", "password": "pw123456"})
    assert response.status_code == 200


def test_students_page_lists_roster_and_protects_route(client):
    assert client.get("/students", follow_redirects=False).status_code == 302
    _login(client)
    course_id = client.post("/courses", json={"name": "VC101", "term": "2026"}).json()["id"]
    client.post(
        f"/courses/{course_id}/roster",
        json={"csv": "学号,姓名,小组\n20260001,张三,G1\n"},
    )
    invite = client.post(f"/courses/{course_id}/enrollment-code", json={}).json()["enrollment_code"]

    response = client.get("/students")
    assert response.status_code == 200
    assert "学生管理" in response.text
    assert "教师创建小组" not in response.text
    assert "prompt(" not in response.text
    assert "enrollment-size" in response.text
    assert invite in response.text
    assert "20260001" in response.text
    assert "张三" in response.text
    assert "/students/" in response.text


def test_teacher_can_create_update_and_delete_student(client):
    _login(client)
    course_id = client.post("/courses", json={"name": "VC101", "term": "2026"}).json()["id"]
    client.post(
        f"/courses/{course_id}/roster",
        json={"csv": "学号,姓名,小组\n20260002,李四,G1\n"},
    )
    db = SessionLocal()
    student_id = db.query(models.Student).filter_by(student_no="20260002").one().id
    db.close()

    page = client.get("/students")
    assert "student-create-form" not in page.text
    assert "新增学生" not in page.text
    assert "student-save" in page.text
    assert "student-delete" in page.text

    updated = client.put(f"/students/{student_id}", json={
        "student_no": "20260003",
        "name": "李四（已修改）",
    })
    assert updated.status_code == 200, updated.text
    assert updated.json()["student_no"] == "20260003"
    assert updated.json()["name"] == "李四（已修改）"

    deleted = client.delete(f"/students/{student_id}")
    assert deleted.status_code == 204
    db = SessionLocal()
    assert db.get(models.Student, student_id) is None
    db.close()

    db = SessionLocal()
    protected = models.Student(course_id=course_id, student_no="20260004", name="王五")
    db.add(protected)
    db.flush()
    assignment = models.Assignment(
        course_id=course_id,
        code="STUDENT1",
        title="历史作业",
        rubric_json=[],
        opens_at=datetime(2026, 1, 1),
        deadline=datetime(2026, 12, 31),
    )
    db.add(assignment)
    db.flush()
    db.add(models.Submission(assignment_id=assignment.id, student_id=protected.id))
    db.commit()
    db.close()
    assert client.delete(f"/students/{protected.id}").status_code == 409


def test_analytics_page_counts_submission_status_and_grade(client):
    _login(client)
    course_id = client.post("/courses", json={"name": "VC101", "term": "2026"}).json()["id"]
    client.post(
        f"/courses/{course_id}/roster",
        json={"csv": "学号,姓名,小组\n20260001,张三,G1\n"},
    )
    db = SessionLocal()
    student = db.query(models.Student).one()
    assignment = models.Assignment(
        course_id=course_id,
        code="ABC12345",
        title="A",
        rubric_json=[],
        opens_at=datetime(2026, 1, 1),
        deadline=datetime(2026, 12, 31),
    )
    db.add(assignment)
    db.flush()
    submission = models.Submission(assignment_id=assignment.id, student_id=student.id, status="evaluated")
    db.add(submission)
    db.flush()
    attempt = models.SubmissionAttempt(
        submission_id=submission.id,
        attempt_no=1,
        package_path="package.zip",
        size_bytes=1,
        manifest_version="1",
    )
    db.add(attempt)
    db.flush()
    db.add(
        models.Evaluation(
            attempt_id=attempt.id,
            grade="A",
            dimension_scores_json=[],
            feedback_json=[],
            flags_json=[],
            evidence_json=[],
        )
    )
    db.commit()
    db.close()

    response = client.get("/analytics")
    assert response.status_code == 200
    assert "数据分析" in response.text
    assert "evaluated" in response.text
    assert "AI 等级分布" in response.text
