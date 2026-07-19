import os
import pathlib

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.responses import FileResponse

from .. import models
from ..config import Settings
from ..db import get_db
from ..deps import get_teacher
from ..errors import ApiError
from ..eval.metrics import compute_metrics
from ..eval.parser import parse_rollout
from .pages import get_teacher_page

router = APIRouter()


def _extract_dir_for_attempt(attempt: models.SubmissionAttempt, settings: Settings) -> str:
    return os.path.join(settings.data_dir, "extracted", str(attempt.id))


def _latest_evaluation(db: Session, attempt: models.SubmissionAttempt | None):
    if attempt is None:
        return None
    return (
        db.query(models.Evaluation)
        .filter_by(attempt_id=attempt.id)
        .order_by(models.Evaluation.created_at.desc())
        .first()
    )


def _override_history(db: Session, target_type: str, target_id: str):
    return (
        db.query(models.GradeOverride)
        .filter_by(target_type=target_type, target_id=target_id)
        .order_by(models.GradeOverride.updated_at.desc())
        .all()
    )


def _current_override(db: Session, target_type: str, target_id: str):
    return (
        db.query(models.GradeOverride)
        .filter_by(target_type=target_type, target_id=target_id)
        .order_by(models.GradeOverride.updated_at.desc())
        .first()
    )


def _final_grade(override, evaluation):
    if override is not None and not override.stale:
        return override.final_grade
    if evaluation is not None:
        return evaluation.grade
    return None


def _safe_extract_root(settings: Settings) -> pathlib.Path:
    return pathlib.Path(os.path.abspath(os.path.join(settings.data_dir, "extracted")))


@router.get("/media/extracted/{path:path}")
def media_extracted(
    path: str,
    request: Request,
    t: models.Teacher = Depends(get_teacher),
):
    settings = request.app.state.settings
    root = _safe_extract_root(settings)
    requested = pathlib.Path(os.path.abspath(os.path.join(root, path)))
    try:
        requested.relative_to(root)
    except ValueError:
        raise ApiError(404, "NOT_FOUND", "文件不存在")
    if not requested.exists() or not requested.is_file():
        raise ApiError(404, "NOT_FOUND", "文件不存在")
    return FileResponse(str(requested))


@router.get("/submissions/{sid}", response_class=HTMLResponse)
def submission_detail(
    request: Request,
    sid: int,
    db: Session = Depends(get_db),
    t: models.Teacher = Depends(get_teacher_page),
):
    from ..main import templates

    submission = db.get(models.Submission, sid)
    if submission is None:
        raise ApiError(404, "NOT_FOUND", "提交不存在")

    assignment = db.get(models.Assignment, submission.assignment_id)
    student = db.get(models.Student, submission.student_id)
    attempt = None
    if submission.current_attempt_id is not None:
        attempt = db.get(models.SubmissionAttempt, submission.current_attempt_id)

    evaluation = _latest_evaluation(db, attempt)

    settings = request.app.state.settings
    timelines = []
    metrics = {}
    code_files = []
    screenshots = []
    if attempt is not None:
        extract_dir = _extract_dir_for_attempt(attempt, settings)
        session_dir = pathlib.Path(extract_dir) / "sessions"
        if session_dir.exists():
            for p in sorted(session_dir.glob("*.jsonl")):
                timelines.append(parse_rollout(str(p)))
        metrics = compute_metrics(timelines)

        root = pathlib.Path(extract_dir)
        if root.exists():
            for p in sorted(root.rglob("*")):
                if p.is_file():
                    rel = p.relative_to(root).as_posix()
                    if rel.startswith("screenshots/"):
                        screenshots.append(rel)
                    else:
                        code_files.append(rel)

    target_type = "individual"
    target_id = f"{submission.assignment_id}:{submission.student_id}"
    override = _current_override(db, target_type, target_id)
    history = _override_history(db, target_type, target_id)

    final_grade = _final_grade(override, evaluation)
    ai_grade = evaluation.grade if evaluation else None

    return templates.TemplateResponse(
        request,
        "submission.html",
        {
            "teacher": t,
            "assignment": assignment,
            "student": student,
            "submission": submission,
            "attempt": attempt,
            "evaluation": evaluation,
            "override": override,
            "history": history,
            "final_grade": final_grade,
            "ai_grade": ai_grade,
            "timelines": timelines,
            "metrics": metrics,
            "code_files": code_files,
            "screenshots": screenshots,
            "media_prefix": f"/media/extracted/{attempt.id}" if attempt else "",
        },
    )


@router.post("/evaluations/{eid}/override")
def evaluation_override(
    request: Request,
    eid: int,
    final_grade: str = Form(...),
    comment: str = Form(""),
    db: Session = Depends(get_db),
    t: models.Teacher = Depends(get_teacher_page),
):
    evaluation = db.get(models.Evaluation, eid)
    if evaluation is None:
        raise ApiError(404, "NOT_FOUND", "评估不存在")

    attempt = db.get(models.SubmissionAttempt, evaluation.attempt_id)
    if attempt is None:
        raise ApiError(404, "NOT_FOUND", "提交不存在")
    submission = db.get(models.Submission, attempt.submission_id)
    if submission is None:
        raise ApiError(404, "NOT_FOUND", "提交不存在")

    if final_grade not in {"A", "B", "C", "D", "E"}:
        raise ApiError(422, "BAD_GRADE", "成绩必须是 A-E")

    target_type = "individual"
    target_id = f"{submission.assignment_id}:{submission.student_id}"

    override = db.query(models.GradeOverride).filter_by(
        target_type=target_type, target_id=target_id
    ).first()
    if override is None:
        override = models.GradeOverride(
            target_type=target_type,
            target_id=target_id,
            final_grade=final_grade,
            comment=comment,
            teacher_id=t.id,
            stale=False,
        )
        db.add(override)
    else:
        override.final_grade = final_grade
        override.comment = comment
        override.teacher_id = t.id
        override.stale = False
    db.commit()

    return RedirectResponse(url=f"/submissions/{submission.id}", status_code=302)


@router.post("/group-evaluations/{gid}/override")
def group_evaluation_override(
    request: Request,
    gid: int,
    final_grade: str = Form(...),
    comment: str = Form(""),
    db: Session = Depends(get_db),
    t: models.Teacher = Depends(get_teacher_page),
):
    geval = db.get(models.GroupEvaluation, gid)
    if geval is None:
        raise ApiError(404, "NOT_FOUND", "小组评估不存在")

    if final_grade not in {"A", "B", "C", "D", "E"}:
        raise ApiError(422, "BAD_GRADE", "成绩必须是 A-E")

    target_type = "group"
    target_id = f"{geval.assignment_id}:{geval.group_id}"

    override = db.query(models.GradeOverride).filter_by(
        target_type=target_type, target_id=target_id
    ).first()
    if override is None:
        override = models.GradeOverride(
            target_type=target_type,
            target_id=target_id,
            final_grade=final_grade,
            comment=comment,
            teacher_id=t.id,
            stale=False,
        )
        db.add(override)
    else:
        override.final_grade = final_grade
        override.comment = comment
        override.teacher_id = t.id
        override.stale = False
    db.commit()

    return RedirectResponse(url=f"/assignments/{geval.assignment_id}/board", status_code=302)
