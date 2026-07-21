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
            }
        )
    return {"student": student, "course": course, "group": group, "rows": rows}
