import json
from datetime import timedelta

from app import models
from app.db import SessionLocal
from app.eval.worker import run_worker_once
from app.utils import utcnow
from app.web.board import _final_grade
from tests.test_courses_roster import _login
from tests.test_eval_pipeline import FakeLLMProvider


def test_changing_evaluation_prompt_requeues_current_submissions(client, settings):
    _login(client)
    course_id = client.post("/courses", json={"name": "C", "term": ""}).json()["id"]
    now = utcnow()
    created = client.post(
        f"/courses/{course_id}/assignments",
        json={
            "title": "A",
            "description": "",
            "opens_at": (now - timedelta(days=1)).isoformat(),
            "deadline": (now + timedelta(days=1)).isoformat(),
            "max_package_mb": 50,
        },
    ).json()

    db = SessionLocal()
    assignment = db.get(models.Assignment, created["id"])
    student = models.Student(course_id=course_id, student_no="s-1", name="Student")
    db.add(student)
    db.flush()
    submission = models.Submission(
        assignment_id=assignment.id, student_id=student.id, status="evaluated"
    )
    db.add(submission)
    db.flush()
    attempt = models.SubmissionAttempt(
        submission_id=submission.id,
        attempt_no=1,
        package_path="data/packages/test.zip",
        size_bytes=1,
        manifest_version="1",
        status="evaluated",
    )
    db.add(attempt)
    db.flush()
    submission.current_attempt_id = attempt.id
    db.add(
        models.Evaluation(
            attempt_id=attempt.id,
            grade="C",
            dimension_scores_json=[],
            rationale="old",
            feedback_json=[],
            flags_json=[],
            evidence_json=[],
            model="test",
            prompt_version="v5",
        )
    )
    db.add(
        models.EvalJob(
            assignment_id=assignment.id,
            kind="individual",
            target_id=attempt.id,
            status="done",
            attempts=1,
        )
    )
    override = models.GradeOverride(
        target_type="individual",
        target_id=f"{assignment.id}:{student.id}",
        final_grade="A",
        comment="old manual grade",
        teacher_id=1,
        stale=False,
    )
    db.add(override)
    db.commit()

    updated = client.put(
        f"/assignments/{assignment.id}/evaluation-config",
        json={
            "evaluation_profile": "generic_experiment",
            "evaluation_instructions": "Teacher requirement: reward experimental evidence.",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["requeued"] == 1

    db.expire_all()
    assert db.get(models.Submission, submission.id).status == "queued"
    assert db.get(models.SubmissionAttempt, attempt.id).status == "queued"
    job = db.query(models.EvalJob).filter_by(target_id=attempt.id).one()
    assert job.status == "queued"
    assert job.attempts == 0
    assert db.query(models.Evaluation).filter_by(attempt_id=attempt.id).count() == 1
    assert db.get(models.GradeOverride, override.id).stale is False

    provider = FakeLLMProvider(
        responses=[
            json.dumps(
                {
                    "grade": "B",
                    "dimension_scores": [
                        {
                            "name": "teacher-defined",
                            "weight": 100,
                            "score": 88,
                            "rationale": "new prompt applied",
                        }
                    ],
                    "evidence": [],
                    "rationale": "new evaluation",
                    "feedback": [],
                    "flags": ["no sessions"],
                }
            )
        ]
    )
    assert run_worker_once(db, provider, settings) == 1
    evaluations = (
        db.query(models.Evaluation)
        .filter_by(attempt_id=attempt.id)
        .order_by(models.Evaluation.id.asc())
        .all()
    )
    assert [item.grade for item in evaluations] == ["C", "B"]
    assert _final_grade(None, evaluations[-1]) == "B"
    assert _final_grade(db.get(models.GradeOverride, override.id), evaluations[-1]) == "A"
    assert db.get(models.Submission, submission.id).status == "evaluated"
    db.close()


def test_unchanged_evaluation_prompt_does_not_requeue(client):
    _login(client)
    course_id = client.post("/courses", json={"name": "C", "term": ""}).json()["id"]
    now = utcnow()
    assignment_id = client.post(
        f"/courses/{course_id}/assignments",
        json={
            "title": "A",
            "description": "",
            "opens_at": (now - timedelta(days=1)).isoformat(),
            "deadline": (now + timedelta(days=1)).isoformat(),
            "max_package_mb": 50,
        },
    ).json()["id"]
    response = client.put(
        f"/assignments/{assignment_id}/evaluation-config",
        json={"evaluation_profile": "generic_experiment", "evaluation_instructions": ""},
    )
    assert response.status_code == 200
    assert response.json()["requeued"] == 0
