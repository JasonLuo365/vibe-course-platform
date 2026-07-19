from sqlalchemy.orm import Session

from .. import models


def enqueue_individual(db: Session, assignment_id: int, attempt_id: int) -> models.EvalJob:
    job = models.EvalJob(assignment_id=assignment_id, kind="individual",
                         target_id=attempt_id, status="queued", attempts=0)
    db.add(job)
    return job

