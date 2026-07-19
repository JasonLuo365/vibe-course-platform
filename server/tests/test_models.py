# server/tests/test_models.py
from app import models
from app.db import SessionLocal
from app.utils import utcnow


def test_create_all_and_insert(client):
    db = SessionLocal()
    t = models.Teacher(username="admin", password_hash="x", display_name="Admin")
    c = models.Course(name="VC101", term="2026秋")
    db.add_all([t, c])
    db.flush()
    g = models.Group(course_id=c.id, name="第1组")
    db.add(g)
    db.flush()
    s = models.Student(course_id=c.id, group_id=g.id, student_no="2024001",
                       name="张三", submit_token_hash="h" * 64)
    a = models.Assignment(course_id=c.id, code="HW3X7K2Q", title="作业3",
                          description="d", rubric_json=[{"name": "prompt质量", "weight": 100, "description": "d"}],
                          opens_at=utcnow(), deadline=utcnow(), max_package_mb=50)
    db.add_all([s, a])
    db.flush()
    sub = models.Submission(assignment_id=a.id, student_id=s.id, status="received")
    db.add(sub)
    db.flush()
    att = models.SubmissionAttempt(submission_id=sub.id, attempt_no=1, submitted_at=utcnow(),
                                   package_path="p.zip", size_bytes=10, manifest_version="1", status="received")
    db.add(att)
    db.flush()
    sub.current_attempt_id = att.id
    ev = models.Evaluation(attempt_id=att.id, grade="B", dimension_scores_json=[], rationale="r",
                           feedback_json=[], flags_json=[], evidence_json=[], model="m", prompt_version="v1")
    ge = models.GroupEvaluation(assignment_id=a.id, group_id=g.id, generation=1, grade="B",
                                rationale="r", contribution_json={}, evidence_json=[])
    ov = models.GradeOverride(target_type="individual", target_id=f"{a.id}:{s.id}",
                              final_grade="A", comment="ok", teacher_id=t.id, stale=False)
    job = models.EvalJob(assignment_id=a.id, kind="individual", target_id=att.id, status="queued", attempts=0)
    db.add_all([ev, ge, ov, job])
    db.commit()
    assert db.query(models.Student).one().student_no == "2024001"
    assert db.query(models.EvalJob).one().status == "queued"
    db.close()

