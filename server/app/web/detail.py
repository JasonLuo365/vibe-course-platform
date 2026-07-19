import html
import os
import pathlib
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Query, Request
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
_SAFE_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


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


def _teacher_conversations(timelines):
    """Expose only student prompts and the final assistant response following each prompt."""
    conversations = []
    for timeline in timelines:
        current = None
        for turn in timeline.turns:
            if turn.kind == "user":
                if current is not None:
                    conversations.append(current)
                current = {
                    "session_id": timeline.session_id,
                    "prompt": turn.text,
                    "prompt_ts": turn.ts,
                    "answer": None,
                    "answer_ts": None,
                }
            elif turn.kind == "assistant" and current is not None:
                current["answer"] = turn.text
                current["answer_ts"] = turn.ts
        if current is not None:
            conversations.append(current)
    return conversations


def _code_tree(code_files: list[str]) -> dict:
    root = {"dirs": {}, "files": []}
    for path in code_files:
        parts = pathlib.PurePosixPath(path).parts
        node = root
        for directory in parts[:-1]:
            node = node["dirs"].setdefault(directory, {"dirs": {}, "files": []})
        node["files"].append({"name": parts[-1], "path": path, "url_path": quote(path)})
    return root


def _read_code_file(extract_dir: str, path: str) -> dict:
    code_root = pathlib.Path(os.path.realpath(os.path.join(extract_dir, "code")))
    requested = pathlib.Path(os.path.realpath(os.path.join(code_root, path)))
    try:
        requested.relative_to(code_root)
    except ValueError:
        raise ApiError(404, "NOT_FOUND", "file not found")
    if not requested.exists() or not requested.is_file():
        raise ApiError(404, "NOT_FOUND", "file not found")
    try:
        raw = requested.read_bytes()
    except OSError:
        raise ApiError(404, "NOT_FOUND", "file not found")
    max_bytes = 100 * 1024
    return {
        "path": path,
        "content": raw[:max_bytes].decode("utf-8", errors="replace"),
        "truncated": len(raw) > max_bytes,
        "total_bytes": len(raw),
    }


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
    if requested.suffix.lower() not in _SAFE_IMAGE_SUFFIXES:
        raise ApiError(404, "NOT_FOUND", "文件不存在")
    return FileResponse(
        str(requested),
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.get("/submissions/{sid}", response_class=HTMLResponse)
def submission_detail(
    request: Request,
    sid: int,
    file: str | None = Query(default=None),
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
    code_files: list[str] = []
    screenshots = []
    if attempt is not None:
        extract_dir = _extract_dir_for_attempt(attempt, settings)
        session_dir = pathlib.Path(extract_dir) / "sessions"
        if session_dir.exists():
            for p in sorted(session_dir.glob("*.jsonl")):
                timelines.append(parse_rollout(str(p)))
        metrics = compute_metrics(timelines)

        root = pathlib.Path(extract_dir)
        code_root = root / "code"
        if root.exists():
            for p in sorted(root.rglob("*")):
                if p.is_file():
                    rel = p.relative_to(root).as_posix()
                    if rel.startswith("screenshots/") and p.suffix.lower() in _SAFE_IMAGE_SUFFIXES:
                        screenshots.append(rel)
                    elif rel.startswith("code/"):
                        code_files.append(rel[5:])

    code_files.sort()
    selected_code = None
    if attempt is not None and code_files:
        selected_code = _read_code_file(extract_dir, file or code_files[0])

    target_type = "individual"
    target_id = f"{submission.assignment_id}:{submission.student_id}"
    override = _current_override(db, target_type, target_id)

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
            "final_grade": final_grade,
            "ai_grade": ai_grade,
            "timelines": timelines,
            "conversations": _teacher_conversations(timelines),
            "metrics": metrics,
            "code_files": code_files,
            "code_tree": _code_tree(code_files),
            "selected_code": selected_code,
            "screenshots": screenshots,
            "media_prefix": f"/media/extracted/{attempt.id}" if attempt else "",
        },
    )


@router.get("/submissions/{sid}/code", response_class=HTMLResponse)
def submission_code(
    request: Request,
    sid: int,
    path: str = Query(...),
    db: Session = Depends(get_db),
    t: models.Teacher = Depends(get_teacher_page),
):
    from ..main import templates

    submission = db.get(models.Submission, sid)
    if submission is None:
        raise ApiError(404, "NOT_FOUND", "提交不存在")

    attempt = None
    if submission.current_attempt_id is not None:
        attempt = db.get(models.SubmissionAttempt, submission.current_attempt_id)
    if attempt is None:
        raise ApiError(404, "NOT_FOUND", "无可用提交")

    settings = request.app.state.settings
    extract_dir = _extract_dir_for_attempt(attempt, settings)
    code_root = pathlib.Path(os.path.realpath(os.path.join(extract_dir, "code")))
    requested = pathlib.Path(os.path.realpath(os.path.join(code_root, path)))

    try:
        requested.relative_to(code_root)
    except ValueError:
        raise ApiError(404, "NOT_FOUND", "文件不存在")

    if not requested.exists() or not requested.is_file():
        raise ApiError(404, "NOT_FOUND", "文件不存在")

    try:
        raw = requested.read_bytes()
    except OSError:
        raise ApiError(404, "NOT_FOUND", "文件不存在")

    MAX_BYTES = 100 * 1024
    truncated = len(raw) > MAX_BYTES
    content = raw[:MAX_BYTES].decode("utf-8", errors="replace")

    return templates.TemplateResponse(
        request,
        "code_view.html",
        {
            "teacher": t,
            "submission": submission,
            "path": path,
            "content": content,
            "truncated": truncated,
            "total_bytes": len(raw),
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

