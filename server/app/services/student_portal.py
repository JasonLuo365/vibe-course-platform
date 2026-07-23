from sqlalchemy.orm import Session

from .. import models


def _evaluation_for_attempt(db: Session, attempt: models.SubmissionAttempt | None):
    if attempt is None:
        return None
    return (
        db.query(models.Evaluation)
        .filter_by(attempt_id=attempt.id)
        .order_by(models.Evaluation.created_at.desc(), models.Evaluation.id.desc())
        .first()
    )


def _group_evaluation_for_assignment(
    db: Session,
    assignment_id: int,
    group_id: int | None,
):
    if group_id is None:
        return None
    return (
        db.query(models.GroupEvaluation)
        .filter_by(assignment_id=assignment_id, group_id=group_id)
        .order_by(models.GroupEvaluation.created_at.desc(), models.GroupEvaluation.id.desc())
        .first()
    )


def _visible_override(db: Session, target_type: str, target_id: str):
    return (
        db.query(models.GradeOverride)
        .filter_by(target_type=target_type, target_id=target_id, stale=False)
        .order_by(models.GradeOverride.updated_at.desc(), models.GradeOverride.id.desc())
        .first()
    )


def dashboard_data(db: Session, student: models.Student) -> dict:
    course = db.get(models.Course, student.course_id)
    group = db.get(models.Group, student.group_id) if student.group_id else None
    assignments = (
        db.query(models.Assignment)
        .filter_by(course_id=student.course_id)
        .order_by(models.Assignment.id)
        .all()
    )
    submissions = (
        db.query(models.Submission)
        .filter_by(student_id=student.id)
        .all()
    )
    submission_by_assignment = {item.assignment_id: item for item in submissions}
    attachments_by_assignment: dict[int, list[models.AssignmentAttachment]] = {}
    if assignments:
        assignment_ids = [item.id for item in assignments]
        for attachment in (
            db.query(models.AssignmentAttachment)
            .filter(models.AssignmentAttachment.assignment_id.in_(assignment_ids))
            .order_by(models.AssignmentAttachment.id)
            .all()
        ):
            attachments_by_assignment.setdefault(attachment.assignment_id, []).append(attachment)
    rows = []
    for assignment in assignments:
        submission = submission_by_assignment.get(assignment.id)
        attempt = (
            db.get(models.SubmissionAttempt, submission.current_attempt_id)
            if submission and submission.current_attempt_id
            else None
        )
        rows.append(
            {
                "assignment": assignment,
                "submission": submission,
                "attempt": attempt,
                "evaluation": _evaluation_for_attempt(db, attempt),
                "attachments": attachments_by_assignment.get(assignment.id, []),
            }
        )
    return {"student": student, "course": course, "group": group, "rows": rows}


def submission_feedback_data(
    db: Session,
    student: models.Student,
    submission: models.Submission,
) -> dict:
    assignment = db.get(models.Assignment, submission.assignment_id)
    group = db.get(models.Group, student.group_id) if student.group_id else None
    attempt = (
        db.get(models.SubmissionAttempt, submission.current_attempt_id)
        if submission.current_attempt_id
        else None
    )
    evaluation = _evaluation_for_attempt(db, attempt)
    group_evaluation = _group_evaluation_for_assignment(
        db, submission.assignment_id, student.group_id
    )
    individual_override = _visible_override(
        db, "individual", f"{submission.assignment_id}:{student.id}"
    )
    group_override = _visible_override(
        db, "group", f"{submission.assignment_id}:{student.group_id}"
    ) if student.group_id else None
    return {
        "assignment": assignment,
        "group": group,
        "submission": submission,
        "attempt": attempt,
        "evaluation": evaluation,
        "group_evaluation": group_evaluation,
        "individual_override": individual_override,
        "group_override": group_override,
    }
