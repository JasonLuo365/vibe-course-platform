"""Read-only reports released to an authenticated student."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..deps import get_student
from ..errors import ApiError

router = APIRouter()


def _override(db: Session, target_type: str, target_id: str):
    return (db.query(models.GradeOverride).filter_by(target_type=target_type, target_id=target_id)
            .order_by(models.GradeOverride.updated_at.desc()).first())


def _individual(db: Session, assignment_id: int, student_id: int):
    submission = db.query(models.Submission).filter_by(assignment_id=assignment_id, student_id=student_id).first()
    if submission is None or submission.current_attempt_id is None:
        return submission, None, None
    attempt = db.get(models.SubmissionAttempt, submission.current_attempt_id)
    evaluation = (db.query(models.Evaluation).filter_by(attempt_id=attempt.id)
                  .order_by(models.Evaluation.created_at.desc()).first()) if attempt else None
    return submission, attempt, evaluation


def _group_evaluation(db: Session, assignment_id: int, group_id: int | None):
    if group_id is None:
        return None
    return (db.query(models.GroupEvaluation).filter_by(assignment_id=assignment_id, group_id=group_id)
            .order_by(models.GroupEvaluation.generation.desc(), models.GroupEvaluation.created_at.desc()).first())


def _individual_state(submission, evaluation) -> str:
    if submission is None:
        return "not_submitted"
    if evaluation is None:
        return "evaluating" if submission.status in {"queued", "evaluating"} else "pending"
    return "published" if evaluation.published_at else "awaiting_publication"


def _group_payload(db: Session, assignment: models.Assignment, student: models.Student, evaluation) -> dict:
    if student.group_id is None:
        return {"state": "not_grouped"}
    group = db.get(models.Group, student.group_id)
    name = group.name if group else ""
    if evaluation is None:
        return {"state": "pending", "group_name": name}
    if evaluation.published_at is None:
        return {"state": "awaiting_publication", "group_name": name}
    override = _override(db, "group", f"{assignment.id}:{student.group_id}")
    adjusted = override if override and not override.stale else None
    return {
        "state": "published", "group_name": name,
        "published_at": evaluation.published_at.isoformat(),
        "grade": adjusted.final_grade if adjusted else evaluation.grade,
        "ai_grade": evaluation.grade,
        "grade_source": "teacher_adjusted" if adjusted else "ai_assisted",
        "teacher_comment": adjusted.comment if adjusted else "",
        "summary": evaluation.rationale,
    }


def _report(db: Session, assignment: models.Assignment, student: models.Student) -> dict:
    submission, attempt, evaluation = _individual(db, assignment.id, student.id)
    state = _individual_state(submission, evaluation)
    group_report = _group_payload(db, assignment, student, _group_evaluation(db, assignment.id, student.group_id))
    result = {"state": state, "assignment": {"code": assignment.code, "title": assignment.title},
              "submission_status": submission.status if submission else "none", "group_report": group_report}
    if state != "published":
        return result
    override = _override(db, "individual", f"{assignment.id}:{student.id}")
    adjusted = override if override and not override.stale else None
    result.update({
        "attempt_no": attempt.attempt_no, "submitted_at": attempt.submitted_at.isoformat(),
        "published_at": evaluation.published_at.isoformat(),
        "grade": adjusted.final_grade if adjusted else evaluation.grade,
        "ai_grade": evaluation.grade,
        "grade_source": "teacher_adjusted" if adjusted else "ai_assisted",
        "teacher_comment": adjusted.comment if adjusted else "",
        "summary": evaluation.rationale,
        "dimension_scores": evaluation.dimension_scores_json,
        "feedback": evaluation.feedback_json,
    })
    return result


@router.get("/api/student/reports")
def list_reports(student: models.Student = Depends(get_student), db: Session = Depends(get_db)):
    assignments = db.query(models.Assignment).filter_by(course_id=student.course_id).order_by(models.Assignment.deadline.desc()).all()
    reports = []
    for assignment in assignments:
        report = _report(db, assignment, student)
        reports.append({
            "assignment_code": assignment.code, "assignment_title": assignment.title,
            "state": report["state"], "submission_status": report["submission_status"],
            "group_report": report["group_report"],
            **({"grade": report["grade"], "published_at": report["published_at"]} if report["state"] == "published" else {}),
        })
    return {"reports": reports}


@router.get("/api/student/reports/{assignment_code}")
def get_report(assignment_code: str, student: models.Student = Depends(get_student), db: Session = Depends(get_db)):
    assignment = db.query(models.Assignment).filter_by(code=assignment_code).first()
    if assignment is None or assignment.course_id != student.course_id:
        raise ApiError(404, "NOT_FOUND", "作业不存在")
    return _report(db, assignment, student)
