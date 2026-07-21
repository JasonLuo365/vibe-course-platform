"""Released evaluation reports are visible only to their owning student."""

from app import models
from app.db import SessionLocal
from app.eval.worker import run_worker_once
from tests.test_eval_pipeline import FakeLLMProvider, _valid_individual_json
from tests.test_web_detail import _setup_course_and_assignment, _upload


def _evaluate_one(client, settings):
    _course_id, tokens, code = _setup_course_and_assignment(client)
    db = SessionLocal()
    student = db.query(models.Student).filter_by(student_no="2024001").one()
    db.close()
    assert _upload(client, tokens[student.student_no], code, student.student_no).status_code == 201
    db = SessionLocal()
    assert run_worker_once(db, FakeLLMProvider(responses=[_valid_individual_json()]), settings) == 1
    evaluation = db.query(models.Evaluation).one()
    db.close()
    return tokens, code, evaluation.id


def test_report_hides_unpublished_evaluation_and_exposes_released_feedback(client, settings):
    tokens, code, evaluation_id = _evaluate_one(client, settings)
    headers = {"Authorization": f"Bearer {tokens['2024001']}"}

    waiting = client.get(f"/api/student/reports/{code}", headers=headers)
    assert waiting.status_code == 200
    assert waiting.json()["state"] == "awaiting_publication"
    assert "grade" not in waiting.json()

    publish = client.post(f"/evaluations/{evaluation_id}/publish", follow_redirects=False)
    assert publish.status_code == 302

    report = client.get(f"/api/student/reports/{code}", headers=headers)
    assert report.status_code == 200
    body = report.json()
    assert body["state"] == "published"
    assert body["grade"] == "B"
    assert body["dimension_scores"]
    assert body["feedback"]
    assert "evidence" not in body
    assert "flags" not in body

    listing = client.get("/api/student/reports", headers=headers)
    assert listing.status_code == 200
    item = next(item for item in listing.json()["reports"] if item["assignment_code"] == code)
    assert item["state"] == "published"
    assert item["grade"] == "B"


def test_student_cannot_read_another_students_report(client, settings):
    tokens, code, evaluation_id = _evaluate_one(client, settings)
    assert client.post(f"/evaluations/{evaluation_id}/publish").status_code == 200

    own = client.get(
        f"/api/student/reports/{code}",
        headers={"Authorization": f"Bearer {tokens['2024002']}"},
    )
    assert own.status_code == 200
    assert own.json()["state"] == "not_submitted"


def test_group_report_is_shared_only_after_its_own_release(client):
    _course_id, tokens, code = _setup_course_and_assignment(client)
    db = SessionLocal()
    assignment = db.query(models.Assignment).filter_by(code=code).one()
    group = db.query(models.Group).filter_by(name="G1").one()
    evaluation = models.GroupEvaluation(
        assignment_id=assignment.id,
        group_id=group.id,
        generation=1,
        grade="A",
        rationale="小组协作和交付质量良好。",
        contribution_json={"members": ["private individual feedback"]},
        evidence_json=[{"private": "evidence"}],
    )
    db.add(evaluation)
    db.commit()
    evaluation_id = evaluation.id
    db.close()

    headers = {"Authorization": f"Bearer {tokens['2024001']}"}
    before = client.get(f"/api/student/reports/{code}", headers=headers)
    assert before.json()["group_report"]["state"] == "awaiting_publication"

    assert client.post(f"/group-evaluations/{evaluation_id}/publish").status_code == 200
    after = client.get(f"/api/student/reports/{code}", headers=headers)
    report = after.json()["group_report"]
    assert report["state"] == "published"
    assert report["grade"] == "A"
    assert "contribution_json" not in report
    assert "evidence" not in report

    other_group = client.get(
        f"/api/student/reports/{code}",
        headers={"Authorization": f"Bearer {tokens['2024003']}"},
    )
    assert other_group.json()["group_report"]["state"] == "pending"
