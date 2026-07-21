"""Student-facing, read-only evaluation reports.

Raw evidence, model metadata, and internal flags intentionally stay in the
teacher review UI.  The student API exposes only the released learning report.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..deps import get_student
from ..errors import ApiError

router = APIRouter()


def _current_override(db: Session, assignment_id: int, student_id: int):
    return (
        db.query(models.GradeOverride)
        .filter_by(target_type="individual", target_id=f"{assignment_id}:{student_id}")
        .order_by(models.GradeOverride.updated_at.desc())
        .first()
    )


def _current_group_override(db: Session, assignment_id: int, group_id: int):
    return (
        db.query(models.GradeOverride)
        .filter_by(target_type="group", target_id=f"{assignment_id}:{group_id}")
        .order_by(models.GradeOverride.updated_at.desc())
        .first()
    )


def _submission_for_assignment(db: Session, assignment_id: int, student_id: int):
    return db.query(models.Submission).filter_by(
        assignment_id=assignment_id, student_id=student_id
    ).first()


def _evaluation_for_submission(db: Session, submission: models.Submission | None):
    if submission is None or submission.current_attempt_id is None:
        return None, None
    attempt = db.get(models.SubmissionAttempt, submission.current_attempt_id)
    if attempt is None:
        return None, None
    evaluation = (
        db.query(models.Evaluation)
        .filter_by(attempt_id=attempt.id)
        .order_by(models.Evaluation.created_at.desc())
        .first()
    )
    return attempt, evaluation


def _report_state(submission, evaluation) -> str:
    if submission is None:
        return "not_submitted"
    if evaluation is None:
        return "evaluating" if submission.status in {"queued", "evaluating"} else "pending"
    return "published" if evaluation.published_at is not None else "awaiting_publication"


def _latest_group_evaluation(db: Session, assignment_id: int, group_id: int | None):
    if group_id is None:
        return None
    return (
        db.query(models.GroupEvaluation)
        .filter_by(assignment_id=assignment_id, group_id=group_id)
        .order_by(models.GroupEvaluation.generation.desc(), models.GroupEvaluation.created_at.desc())
        .first()
    )


def _group_report_payload(
    db: Session,
    assignment: models.Assignment,
    student: models.Student,
    evaluation: models.GroupEvaluation | None,
) -> dict:
    if student.group_id is None:
        return {"state": "not_grouped"}
    group = db.get(models.Group, student.group_id)
    if evaluation is None:
        return {"state": "pending", "group_name": group.name if group else ""}
    if evaluation.published_at is None:
        return {"state": "awaiting_publication", "group_name": group.name if group else ""}
    override = _current_group_override(db, assignment.id, student.group_id)
    final_override = override if override is not None and not override.stale else None
    # Do not return contribution_json: it embeds other members' individual
    # assessments. Group members receive only the common group conclusion.
    return {
        "state": "published",
        "group_name": group.name if group else "",
        "published_at": evaluation.published_at.isoformat(),
        "grade": final_override.final_grade if final_override else evaluation.grade,
        "ai_grade": evaluation.grade,
        "grade_source": "teacher_adjusted" if final_override else "ai_assisted",
        "teacher_comment": final_override.comment if final_override else "",
        "summary": evaluation.rationale,
    }


def _report_payload(
    db: Session,
    assignment: models.Assignment,
    student: models.Student,
    submission: models.Submission,
    attempt: models.SubmissionAttempt,
    evaluation: models.Evaluation,
) -> dict:
    override = _current_override(db, assignment.id, student.id)
    final_override = override if override is not None and not override.stale else None
    return {
        "state": "published",
        "assignment": {"code": assignment.code, "title": assignment.title},
        "attempt_no": attempt.attempt_no,
        "submitted_at": attempt.submitted_at.isoformat(),
        "published_at": evaluation.published_at.isoformat(),
        "grade": final_override.final_grade if final_override else evaluation.grade,
        "ai_grade": evaluation.grade,
        "grade_source": "teacher_adjusted" if final_override else "ai_assisted",
        "teacher_comment": final_override.comment if final_override else "",
        "summary": evaluation.rationale,
        "dimension_scores": evaluation.dimension_scores_json,
        "feedback": evaluation.feedback_json,
    }


@router.get("/api/student/reports")
def list_reports(
    student: models.Student = Depends(get_student),
    db: Session = Depends(get_db),
):
    assignments = (
        db.query(models.Assignment)
        .filter_by(course_id=student.course_id)
        .order_by(models.Assignment.deadline.desc())
        .all()
    )
    reports = []
    for assignment in assignments:
        submission = _submission_for_assignment(db, assignment.id, student.id)
        attempt, evaluation = _evaluation_for_submission(db, submission)
        state = _report_state(submission, evaluation)
        item = {
            "assignment_code": assignment.code,
            "assignment_title": assignment.title,
            "state": state,
            "submission_status": submission.status if submission else "none",
        }
        if state == "published":
            override = _current_override(db, assignment.id, student.id)
            item["grade"] = override.final_grade if override and not override.stale else evaluation.grade
            item["published_at"] = evaluation.published_at.isoformat()
        item["group_report"] = _group_report_payload(
            db, assignment, student, _latest_group_evaluation(db, assignment.id, student.group_id)
        )
        reports.append(item)
    return {"reports": reports}


@router.get("/api/student/reports/{assignment_code}")
def get_report(
    assignment_code: str,
    student: models.Student = Depends(get_student),
    db: Session = Depends(get_db),
):
    assignment = db.query(models.Assignment).filter_by(code=assignment_code).first()
    if assignment is None or assignment.course_id != student.course_id:
        raise ApiError(404, "NOT_FOUND", "作业不存在")

    submission = _submission_for_assignment(db, assignment.id, student.id)
    attempt, evaluation = _evaluation_for_submission(db, submission)
    state = _report_state(submission, evaluation)
    group_report = _group_report_payload(
        db, assignment, student, _latest_group_evaluation(db, assignment.id, student.group_id)
    )
    if state != "published":
        result = {
            "state": state,
            "assignment": {"code": assignment.code, "title": assignment.title},
            "submission_status": submission.status if submission else "none",
            "group_report": group_report,
        }
        return result
    result = _report_payload(db, assignment, student, submission, attempt, evaluation)
    result["group_report"] = group_report
    return result
