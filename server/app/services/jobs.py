from sqlalchemy.orm import Session

from .. import models


def enqueue_individual(db: Session, assignment_id: int, attempt_id: int) -> models.EvalJob:
    job = models.EvalJob(assignment_id=assignment_id, kind="individual",
                         target_id=attempt_id, status="queued", attempts=0)
    db.add(job)
    return job


def requeue_assignment_current_attempts(db: Session, assignment_id: int) -> int:
    """Re-evaluate every student's current submission after scoring rules change.

    Historical attempts and evaluations stay intact for audit purposes.  The
    worker will append a new evaluation for the current attempt, which is what
    all teacher/student views already select as the latest result.
    """
    submissions = db.query(models.Submission).filter_by(assignment_id=assignment_id).all()
    requeued = 0
    for submission in submissions:
        if submission.current_attempt_id is None:
            continue
        attempt = db.get(models.SubmissionAttempt, submission.current_attempt_id)
        if attempt is None:
            continue

        job = (
            db.query(models.EvalJob)
            .filter_by(
                assignment_id=assignment_id,
                kind="individual",
                target_id=attempt.id,
            )
            .order_by(models.EvalJob.id.desc())
            .first()
        )
        if job is None:
            enqueue_individual(db, assignment_id, attempt.id)
        else:
            job.status = "queued"
            job.attempts = 0
            job.last_error = None

        attempt.status = "queued"
        attempt.error = None
        submission.status = "queued"
        submission.error = None

        # A teacher's saved grade remains authoritative.  Re-evaluation only
        # replaces the previous system assessment for students without one.
        requeued += 1
    return requeued
