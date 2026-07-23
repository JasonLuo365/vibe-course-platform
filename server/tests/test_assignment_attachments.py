from pathlib import Path

from app import models
from app.db import SessionLocal
from app.security import hash_password
from tests.test_auth import _mk_teacher


def _login_teacher(client):
    _mk_teacher()
    response = client.post("/login", json={"username": "admin", "password": "pw123456"})
    assert response.status_code == 200


def test_teacher_can_create_assignment_with_multiple_reference_files(client, settings):
    _login_teacher(client)
    course_id = client.post("/courses", json={"name": "软件工程", "term": "2026 夏"}).json()["id"]
    response = client.post(
        "/assignments/new",
        data={
            "course_id": str(course_id),
            "title": "实验说明",
            "description": "请完成实验并提交报告。",
            "opens_at": "2026-07-20T08:00",
            "deadline": "2026-07-30T23:59",
            "max_package_mb": "50",
            "evaluation_profile": "generic_experiment",
            "evaluation_instructions": "",
        },
        files=[
            ("attachments", ("任务说明.md", b"assignment brief", "text/markdown")),
            ("attachments", ("sample.csv", b"name,score\nAlice,100\n", "text/csv")),
        ],
        follow_redirects=False,
    )
    assert response.status_code == 302

    db = SessionLocal()
    assignment = db.query(models.Assignment).one()
    attachments = (
        db.query(models.AssignmentAttachment)
        .filter_by(assignment_id=assignment.id)
        .order_by(models.AssignmentAttachment.id)
        .all()
    )
    assert [item.original_name for item in attachments] == ["任务说明.md", "sample.csv"]
    assert all(item.stored_name != item.original_name for item in attachments)
    attachment_dir = Path(settings.data_dir) / "assignment_attachments" / str(assignment.id)
    assert all((attachment_dir / item.stored_name).is_file() for item in attachments)

    student = models.Student(
        course_id=course_id,
        student_no="20260001",
        name="学生甲",
        password_hash=hash_password("Student01"),
    )
    db.add(student)
    db.commit()
    attachment_id = attachments[0].id
    db.close()

    logged_in = client.post(
        "/student/login",
        json={"student_no": "20260001", "password": "Student01"},
    )
    assert logged_in.status_code == 200
    dashboard = client.get("/student")
    assert "任务说明.md" in dashboard.text
    downloaded = client.get(f"/student/assignment-attachments/{attachment_id}")
    assert downloaded.status_code == 200
    assert downloaded.content == b"assignment brief"
    assert "attachment" in downloaded.headers["content-disposition"]
