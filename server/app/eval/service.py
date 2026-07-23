import logging
import os
from glob import glob
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models
from ..config import Settings, get_settings
from .artifacts import collect_visual_evidence
from .evaluator import EvalError, code_digest, evaluate_group, evaluate_individual
from .metrics import compute_metrics
from .parser import parse_rollout
from .prompts import PROMPT_VERSION, effective_rubric

logger = logging.getLogger(__name__)

def _settings_or_default(settings: Settings | None) -> Settings:
    return settings if settings is not None else get_settings()


def _extract_dir_for_attempt(attempt: models.SubmissionAttempt, settings: Settings) -> str:
    return os.path.join(settings.data_dir, "extracted", str(attempt.id))


def _parse_sessions(extract_dir: str) -> list:
    pattern = os.path.join(extract_dir, "sessions", "*.jsonl")
    paths = sorted(glob(pattern))
    return [parse_rollout(p) for p in paths]


def _compute_attempt_metrics(attempt: models.SubmissionAttempt, settings: Settings) -> dict:
    timelines = _parse_sessions(_extract_dir_for_attempt(attempt, settings))
    return compute_metrics(timelines)


def _evaluation_to_dict(ev: models.Evaluation, student_no: str) -> dict[str, Any]:
    return {
        "student_no": student_no,
        "attempt_id": ev.attempt_id,
        "grade": ev.grade,
        "dimension_scores": ev.dimension_scores_json,
        "rationale": ev.rationale,
        "feedback": ev.feedback_json,
        "flags": ev.flags_json,
        "evidence": ev.evidence_json,
        "model": ev.model,
        "prompt_version": ev.prompt_version,
    }


def _next_group_generation(db: Session, assignment_id: int, group_id: int) -> int:
    max_gen = (
        db.query(func.coalesce(func.max(models.GroupEvaluation.generation), 0))
        .filter_by(assignment_id=assignment_id, group_id=group_id)
        .scalar()
    )
    return max_gen + 1


def _group_project_digest(
    member_attempts: list[tuple[models.Student, models.SubmissionAttempt]],
    settings: Settings,
    max_chars: int = 16000,
) -> str:
    """Provide the group evaluator with actual submitted artifacts, not just AI summaries."""
    parts: list[str] = []
    seen: set[str] = set()
    for member, attempt in member_attempts:
        digest = code_digest(_extract_dir_for_attempt(attempt, settings), max_chars=8000)
        if digest in seen:
            continue
        seen.add(digest)
        parts.append(f"=== {member.student_no} 提交的最终项目 ===\n{digest}")
        if len("\n\n".join(parts)) >= max_chars:
            break
    full = "\n\n".join(parts)
    return full[:max_chars]


def evaluate_attempt(
    db: Session,
    attempt: models.SubmissionAttempt,
    provider,
    settings: Settings | None = None,
) -> models.Evaluation:
    settings = _settings_or_default(settings)
    extract_dir = _extract_dir_for_attempt(attempt, settings)
    timelines = _parse_sessions(extract_dir)
    digest = code_digest(extract_dir)
    visual_evidence = (
        collect_visual_evidence(extract_dir)
        if getattr(provider, "supports_vision", False)
        else []
    )
    metrics = compute_metrics(timelines)

    submission = db.get(models.Submission, attempt.submission_id)
    assignment = db.get(models.Assignment, submission.assignment_id) if submission else None
    rubric = effective_rubric(assignment.rubric_json if assignment else [])
    profile = (assignment.evaluation_profile if assignment else None) or "generic_experiment"
    instructions = (assignment.evaluation_instructions if assignment else None) or ""

    try:
        result = evaluate_individual(
            timelines,
            digest,
            metrics,
            rubric,
            provider,
            profile=profile,
            custom_instructions=instructions,
            visual_evidence=visual_evidence,
        )
    except EvalError as e:
        error = str(e)
        attempt.status = "failed"
        attempt.error = error[:2000]
        if submission is not None:
            submission.status = "failed"
            submission.error = error[:2000]
        db.commit()
        raise

    ev = models.Evaluation(
        attempt_id=attempt.id,
        grade=result["grade"],
        dimension_scores_json=result["dimension_scores"],
        rationale=result["rationale"],
        feedback_json=result["feedback"],
        flags_json=result["flags"],
        evidence_json=result["evidence"],
        model=getattr(provider, "model", settings.llm_model),
        prompt_version=result.get("prompt_version", PROMPT_VERSION),
        prompt_profile=profile,
        prompt_instructions=instructions,
    )
    db.add(ev)

    attempt.status = "evaluated"
    attempt.error = None
    if submission is not None:
        submission.status = "evaluated"
        submission.error = None
    db.commit()

    try:
        _maybe_evaluate_group(db, attempt, provider, settings=settings)
    except Exception:
        logger.exception("Group evaluation failed for attempt %s", attempt.id)
    return ev


def _maybe_evaluate_group(
    db: Session,
    attempt: models.SubmissionAttempt,
    provider,
    settings: Settings | None = None,
) -> models.GroupEvaluation | None:
    settings = _settings_or_default(settings)
    submission = db.get(models.Submission, attempt.submission_id)
    if submission is None:
        return None
    student = db.get(models.Student, submission.student_id)
    if student is None or student.group_id is None:
        return None

    assignment_id = submission.assignment_id
    group_id = student.group_id
    assignment = db.get(models.Assignment, assignment_id)
    rubric = effective_rubric(assignment.rubric_json if assignment else [])
    profile = (assignment.evaluation_profile if assignment else None) or "generic_experiment"
    instructions = (assignment.evaluation_instructions if assignment else None) or ""

    members = db.query(models.Student).filter_by(group_id=group_id).all()
    member_attempts: list[tuple[models.Student, models.SubmissionAttempt]] = []
    for member in members:
        sub = (
            db.query(models.Submission)
            .filter_by(assignment_id=assignment_id, student_id=member.id)
            .first()
        )
        if not sub or not sub.current_attempt_id:
            return None
        att = db.get(models.SubmissionAttempt, sub.current_attempt_id)
        if att is None or att.status != "evaluated":
            return None
        member_attempts.append((member, att))

    member_evals: list[dict[str, Any]] = []
    merged_metrics: dict[str, Any] = {
        "sessions": 0,
        "turns": 0,
        "user_turns": 0,
        "duration_min": 0,
        "error_fix_cycles": 0,
        "files_touched": 0,
    }
    for member, att in member_attempts:
        ev = (
            db.query(models.Evaluation)
            .filter_by(attempt_id=att.id)
            .order_by(models.Evaluation.created_at.desc())
            .first()
        )
        if ev is None:
            return None
        member_evals.append(_evaluation_to_dict(ev, member.student_no))
        metrics = _compute_attempt_metrics(att, settings)
        merged_metrics["sessions"] += metrics["sessions"]
        merged_metrics["turns"] += metrics["turns"]
        merged_metrics["user_turns"] += metrics["user_turns"]
        merged_metrics["duration_min"] = max(merged_metrics["duration_min"], metrics["duration_min"])
        merged_metrics["error_fix_cycles"] += metrics["error_fix_cycles"]
        merged_metrics["files_touched"] += metrics["files_touched"]

    project_digest = _group_project_digest(member_attempts, settings)
    result = evaluate_group(
        member_evals,
        merged_metrics,
        rubric,
        provider,
        profile=profile,
        custom_instructions=instructions,
        project_digest=project_digest,
    )
    generation = _next_group_generation(db, assignment_id, group_id)
    ge = models.GroupEvaluation(
        assignment_id=assignment_id,
        group_id=group_id,
        generation=generation,
        grade=result["grade"],
        rationale=result["rationale"],
        contribution_json={
            "members": member_evals,
            "missing": [],
            "dimension_scores": result["dimension_scores"],
            "feedback": result["feedback"],
            "flags": result["flags"],
        },
        evidence_json=result.get("evidence", []),
        prompt_version=result.get("prompt_version", PROMPT_VERSION),
        prompt_profile=profile,
        prompt_instructions=instructions,
    )
    db.add(ge)
    db.commit()
    return ge


def evaluate_group_job(
    db: Session,
    assignment_id: int,
    group_id: int,
    provider,
    missing: list[models.Student] | None = None,
    settings: Settings | None = None,
) -> int:
    settings = _settings_or_default(settings)
    missing = missing or []
    assignment = db.get(models.Assignment, assignment_id)
    rubric = effective_rubric(assignment.rubric_json if assignment else [])
    profile = (assignment.evaluation_profile if assignment else None) or "generic_experiment"
    instructions = (assignment.evaluation_instructions if assignment else None) or ""

    members = db.query(models.Student).filter_by(group_id=group_id).all()
    member_attempts: list[tuple[models.Student, models.SubmissionAttempt]] = []
    for member in members:
        sub = (
            db.query(models.Submission)
            .filter_by(assignment_id=assignment_id, student_id=member.id)
            .first()
        )
        if not sub or not sub.current_attempt_id:
            continue
        att = db.get(models.SubmissionAttempt, sub.current_attempt_id)
        if att is None or att.status != "evaluated":
            continue
        member_attempts.append((member, att))

    if not member_attempts:
        return 0

    member_evals: list[dict[str, Any]] = []
    merged_metrics: dict[str, Any] = {
        "sessions": 0,
        "turns": 0,
        "user_turns": 0,
        "duration_min": 0,
        "error_fix_cycles": 0,
        "files_touched": 0,
    }
    for member, att in member_attempts:
        ev = (
            db.query(models.Evaluation)
            .filter_by(attempt_id=att.id)
            .order_by(models.Evaluation.created_at.desc())
            .first()
        )
        if ev is None:
            continue
        member_evals.append(_evaluation_to_dict(ev, member.student_no))
        metrics = _compute_attempt_metrics(att, settings)
        merged_metrics["sessions"] += metrics["sessions"]
        merged_metrics["turns"] += metrics["turns"]
        merged_metrics["user_turns"] += metrics["user_turns"]
        merged_metrics["duration_min"] = max(merged_metrics["duration_min"], metrics["duration_min"])
        merged_metrics["error_fix_cycles"] += metrics["error_fix_cycles"]
        merged_metrics["files_touched"] += metrics["files_touched"]

    if not member_evals:
        return 0

    project_digest = _group_project_digest(member_attempts, settings)
    result = evaluate_group(
        member_evals,
        merged_metrics,
        rubric,
        provider,
        profile=profile,
        custom_instructions=instructions,
        project_digest=project_digest,
    )
    rationale = result["rationale"]
    if missing:
        rationale = "缺员: " + ", ".join(m.student_no for m in missing) + "\n" + rationale

    generation = _next_group_generation(db, assignment_id, group_id)
    ge = models.GroupEvaluation(
        assignment_id=assignment_id,
        group_id=group_id,
        generation=generation,
        grade=result["grade"],
        rationale=rationale,
        contribution_json={
            "members": member_evals,
            "missing": [m.student_no for m in missing],
            "dimension_scores": result["dimension_scores"],
            "feedback": result["feedback"],
            "flags": result["flags"],
        },
        evidence_json=result.get("evidence", []),
        prompt_version=result.get("prompt_version", PROMPT_VERSION),
        prompt_profile=profile,
        prompt_instructions=instructions,
    )
    db.add(ge)
    db.commit()
    return 1
