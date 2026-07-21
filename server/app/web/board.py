from sqlalchemy.orm import Session

from .. import models


def _latest_evaluation(db: Session, attempt: models.SubmissionAttempt | None):
    if attempt is None:
        return None
    return (
        db.query(models.Evaluation)
        .filter_by(attempt_id=attempt.id)
        .order_by(models.Evaluation.created_at.desc())
        .first()
    )


def _override_for_student(db: Session, assignment_id: int, student_id: int):
    return (
        db.query(models.GradeOverride)
        .filter_by(
            target_type="individual",
            target_id=f"{assignment_id}:{student_id}",
        )
        .order_by(models.GradeOverride.updated_at.desc())
        .first()
    )


def _final_grade(override, evaluation):
    if override is not None and not override.stale:
        return override.final_grade
    if evaluation is not None:
        return evaluation.grade
    return None


def _cell_status(submission: models.Submission | None):
    if submission is None:
        return "none"
    return submission.status or "none"


def board_data(db: Session, assignment: models.Assignment) -> dict:
    """Build the data structure rendered by the assignment board."""
    groups = (
        db.query(models.Group)
        .filter_by(course_id=assignment.course_id)
        .order_by(models.Group.name)
        .all()
    )

    # Also include students without a group under a synthetic "未分组" bucket.
    grouped_students = set()
    group_rows = []
    for group in groups:
        group_evaluation = (
            db.query(models.GroupEvaluation)
            .filter_by(assignment_id=assignment.id, group_id=group.id)
            .order_by(models.GroupEvaluation.generation.desc(), models.GroupEvaluation.created_at.desc())
            .first()
        )
        group_override = (
            db.query(models.GradeOverride)
            .filter_by(target_type="group", target_id=f"{assignment.id}:{group.id}")
            .order_by(models.GradeOverride.updated_at.desc())
            .first()
        )
        members = []
        students = (
            db.query(models.Student)
            .filter_by(group_id=group.id, course_id=assignment.course_id)
            .order_by(models.Student.student_no)
            .all()
        )
        for student in students:
            grouped_students.add(student.id)
            submission = (
                db.query(models.Submission)
                .filter_by(assignment_id=assignment.id, student_id=student.id)
                .first()
            )
            attempt = None
            if submission is not None and submission.current_attempt_id is not None:
                attempt = db.get(models.SubmissionAttempt, submission.current_attempt_id)
            evaluation = _latest_evaluation(db, attempt)
            override = _override_for_student(db, assignment.id, student.id)
            members.append(
                {
                    "student": student,
                    "submission": submission,
                    "attempt": attempt,
                    "evaluation": evaluation,
                    "override": override,
                    "final_grade": _final_grade(override, evaluation),
                    "cell_status": _cell_status(submission),
                    "stale": bool(override is not None and override.stale),
                }
            )
        group_rows.append({
            "group": group,
            "members": members,
            "group_evaluation": group_evaluation,
            "group_final_grade": _final_grade(group_override, group_evaluation),
        })

    # Ungrouped students.
    ungrouped = (
        db.query(models.Student)
        .filter_by(course_id=assignment.course_id, group_id=None)
        .order_by(models.Student.student_no)
        .all()
    )
    if ungrouped:
        members = []
        for student in ungrouped:
            submission = (
                db.query(models.Submission)
                .filter_by(assignment_id=assignment.id, student_id=student.id)
                .first()
            )
            attempt = None
            if submission is not None and submission.current_attempt_id is not None:
                attempt = db.get(models.SubmissionAttempt, submission.current_attempt_id)
            evaluation = _latest_evaluation(db, attempt)
            override = _override_for_student(db, assignment.id, student.id)
            members.append(
                {
                    "student": student,
                    "submission": submission,
                    "attempt": attempt,
                    "evaluation": evaluation,
                    "override": override,
                    "final_grade": _final_grade(override, evaluation),
                    "cell_status": _cell_status(submission),
                    "stale": bool(override is not None and override.stale),
                }
            )
        group_rows.append({
            "group": None,
            "members": members,
            "group_evaluation": None,
            "group_final_grade": None,
        })

    progress = _progress(db, assignment.id)
    return {"assignment": assignment, "groups": group_rows, "progress": progress}


def _progress(db: Session, assignment_id: int) -> dict:
    subs = db.query(models.Submission).filter_by(assignment_id=assignment_id).all()
    total = len(subs)
    evaluated = sum(1 for s in subs if s.status == "evaluated")
    failed = sum(1 for s in subs if s.status == "failed")
    queued = total - evaluated - failed
    return {
        "total_submissions": total,
        "evaluated": evaluated,
        "failed": failed,
        "queued": queued,
    }


def progress_for_assignment(db: Session, assignment_id: int) -> dict:
    return _progress(db, assignment_id)
