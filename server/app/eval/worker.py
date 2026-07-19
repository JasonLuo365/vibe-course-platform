import asyncio
import logging
from datetime import timedelta

from sqlalchemy.orm import Session

from .. import models
from ..config import Settings, get_settings
from ..db import SessionLocal
from ..eval.llm import OpenAICompatProvider
from ..utils import utcnow
from .service import evaluate_attempt, evaluate_group_job

logger = logging.getLogger(__name__)


def _now():
    """Time source used by the worker; exposed for tests to patch backoff checks."""
    return utcnow()


def _settings_or_default(settings: Settings | None) -> Settings:
    return settings if settings is not None else get_settings()


def claim_next_job(db: Session) -> models.EvalJob | None:
    now = _now()

    job = (
        db.query(models.EvalJob)
        .filter_by(status="queued")
        .order_by(models.EvalJob.created_at.asc())
        .first()
    )
    if job is not None:
        return job

    running = (
        db.query(models.EvalJob)
        .filter_by(status="running")
        .filter(models.EvalJob.attempts < 3)
        .order_by(models.EvalJob.created_at.asc())
        .all()
    )
    for job in running:
        backoff_seconds = job.attempts * 60
        if job.updated_at is None:
            return job
        if job.updated_at + timedelta(seconds=backoff_seconds) <= now:
            return job
    return None


def run_worker_once(db: Session, provider, settings: Settings | None = None) -> int:
    settings = _settings_or_default(settings)
    job = claim_next_job(db)
    if job is not None:
        attempt = db.get(models.SubmissionAttempt, job.target_id)
        if attempt is None:
            job.status = "failed"
            job.last_error = "target attempt not found"
            db.commit()
            return 0

        job.status = "running"
        job.attempts += 1
        job.updated_at = _now()

        attempt.status = "evaluating"
        attempt.error = None
        submission = db.get(models.Submission, attempt.submission_id)
        if submission is not None:
            submission.status = "evaluating"
            submission.error = None
        db.commit()

        try:
            evaluate_attempt(db, attempt, provider, settings=settings)
            job.status = "done"
            job.last_error = None
            db.commit()
            return 1
        except Exception as e:
            error = str(e)
            job.last_error = error[:2000]
            if job.attempts >= 3:
                job.status = "failed"
                attempt.status = "failed"
                attempt.error = error[:2000]
                if submission is not None:
                    submission.status = "failed"
                    submission.error = error[:2000]
            else:
                # Remain "running"; claim_next_job will re-claim after backoff.
                job.status = "running"
            db.commit()
            return 0

    # Deadline sweep for incomplete groups.
    return _deadline_sweep(db, provider, settings)


def _deadline_sweep(db: Session, provider, settings: Settings) -> int:
    now = _now()
    count = 0
    past_assignments = (
        db.query(models.Assignment).filter(models.Assignment.deadline < now).all()
    )
    for assignment in past_assignments:
        groups = db.query(models.Group).filter_by(course_id=assignment.course_id).all()
        for group in groups:
            members = db.query(models.Student).filter_by(group_id=group.id).all()
            if not members:
                continue

            statuses: list[tuple[models.Student, str | None]] = []
            for member in members:
                sub = (
                    db.query(models.Submission)
                    .filter_by(assignment_id=assignment.id, student_id=member.id)
                    .first()
                )
                if not sub or not sub.current_attempt_id:
                    statuses.append((member, None))
                    continue
                att = db.get(models.SubmissionAttempt, sub.current_attempt_id)
                statuses.append((member, att.status if att else None))

            evaluated_statuses = [s for _, s in statuses if s == "evaluated"]
            if not evaluated_statuses:
                continue
            if all(s == "evaluated" for _, s in statuses):
                continue

            # Only sweep once per group to avoid duplicate evaluations.
            existing = (
                db.query(models.GroupEvaluation)
                .filter_by(assignment_id=assignment.id, group_id=group.id)
                .first()
            )
            if existing is not None:
                continue

            missing = [m for m, s in statuses if s != "evaluated"]
            try:
                count += evaluate_group_job(
                    db, assignment.id, group.id, provider, missing=missing, settings=settings
                )
            except Exception as e:
                logger.exception("Deadline group eval failed for group %s: %s", group.id, e)
    return count


async def worker_loop(app):
    settings = app.state.settings
    provider = OpenAICompatProvider(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
    )
    try:
        while True:
            try:
                db = SessionLocal()
                try:
                    await asyncio.to_thread(run_worker_once, db, provider, settings)
                finally:
                    db.close()
            except Exception as e:
                logger.exception("Worker iteration failed: %s", e)
            await asyncio.sleep(2)
    finally:
        provider.close()

