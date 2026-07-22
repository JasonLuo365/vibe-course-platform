import html
import io
import mimetypes
import os
import pathlib
import re
import xml.etree.ElementTree as ET
import zipfile
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
from ..eval.parser import (
    extract_history_envelope_user_prompts,
    is_displayable_human_prompt,
    parse_rollout,
)
from ..utils import utcnow
from .pages import get_teacher_page

router = APIRouter()
_SAFE_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
_TEXT_REPORT_SUFFIXES = {".md", ".txt", ".rst", ".csv", ".json", ".html", ".htm"}
_OFFICE_REPORT_SUFFIXES = {".docx", ".odt", ".pptx", ".xlsx"}
_LEGACY_OFFICE_SUFFIXES = {".doc", ".ppt", ".xls"}
_EMBEDDED_REPORT_SUFFIXES = {".pdf"}
_REPORT_DOWNLOAD_SUFFIXES = (
    _TEXT_REPORT_SUFFIXES
    | _OFFICE_REPORT_SUFFIXES
    | _LEGACY_OFFICE_SUFFIXES
    | _EMBEDDED_REPORT_SUFFIXES
    | _SAFE_IMAGE_SUFFIXES
)
_REPORT_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


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


def _is_displayable_prompt(text: str) -> bool:
    """Compatibility wrapper for the shared prompt-safety rule."""
    return is_displayable_human_prompt(text)


def _embedded_history_prompts(text: str) -> list[str]:
    """Extract human prompts from Codex's history-envelope records.

    Codex may place earlier conversation turns inside a synthetic ``user``
    record when it resumes an approval or assessment context. The enclosing
    record is intentionally hidden by :func:`_is_displayable_prompt`, but its
    labelled ``[N] user:`` entries are genuine student requests. Only those
    labelled entries are returned; system, developer, assistant and tool
    blocks remain private.
    """
    entries = extract_history_envelope_user_prompts(text)
    return [prompt for _index, prompt in entries] if entries is not None else []


def _teacher_conversations(timelines):
    """Group safe prompt/final-answer pairs by source session."""
    conversations = []
    for timeline in timelines:
        session = {"session_id": timeline.session_id, "prompt_pairs": []}
        current = None
        embedded_prompts_seen: set[str] = set()
        for turn in timeline.turns:
            if turn.kind == "user":
                if current is not None:
                    session["prompt_pairs"].append(current)
                if turn.from_history_envelope:
                    # The matching assistant reply is not present as a
                    # separate raw turn, so never attach a later unrelated
                    # reply to an extracted historical prompt.
                    if _is_displayable_prompt(turn.text):
                        session["prompt_pairs"].append({
                            "prompt": turn.text,
                            "prompt_ts": turn.ts,
                            "answer": None,
                            "answer_ts": None,
                        })
                    current = None
                    continue
                embedded_prompts = _embedded_history_prompts(turn.text)
                if embedded_prompts:
                    # History envelopes repeat earlier messages and do not
                    # carry a reliable matching final answer.
                    for prompt in embedded_prompts:
                        normalized = " ".join(prompt.split())
                        if normalized in embedded_prompts_seen:
                            continue
                        embedded_prompts_seen.add(normalized)
                        session["prompt_pairs"].append({
                            "prompt": prompt,
                            "prompt_ts": turn.ts,
                            "answer": None,
                            "answer_ts": None,
                        })
                    current = None
                    continue
                if not _is_displayable_prompt(turn.text):
                    current = None
                    continue
                current = {
                    "prompt": turn.text,
                    "prompt_ts": turn.ts,
                    "answer": None,
                    "answer_ts": None,
                }
            elif turn.kind == "assistant" and current is not None:
                current["answer"] = turn.text
                current["answer_ts"] = turn.ts
        if current is not None:
            session["prompt_pairs"].append(current)
        if session["prompt_pairs"]:
            conversations.append(session)
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


def _xml_text(raw: bytes, members: list[str]) -> str:
    """Extract readable text from XML-based office files without external tools."""
    parts: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for name in members:
                if name not in archive.namelist():
                    continue
                root = ET.fromstring(archive.read(name))
                lines: list[str] = []
                for node in root.iter():
                    tag = node.tag.rsplit("}", 1)[-1]
                    if tag == "t" and node.text:
                        lines.append(node.text)
                    elif tag in {"tab", "tabStop"}:
                        lines.append("\t")
                    elif tag in {"br", "cr", "p"}:
                        lines.append("\n")
                text = "".join(lines)
                if text.strip():
                    parts.append(text)
    except (ET.ParseError, OSError, ValueError, zipfile.BadZipFile):
        return ""
    return "\n\n".join(parts)


def _office_report_text(raw: bytes, suffix: str) -> str:
    if suffix == ".docx":
        return _xml_text(raw, ["word/document.xml"])
    if suffix == ".odt":
        return _xml_text(raw, ["content.xml"])
    if suffix == ".pptx":
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                slides = sorted(name for name in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name))
        except (OSError, ValueError, zipfile.BadZipFile):
            return ""
        return _xml_text(raw, slides)
    if suffix == ".xlsx":
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                members = ["xl/sharedStrings.xml"] + sorted(
                    name for name in archive.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)
                )
        except (OSError, ValueError, zipfile.BadZipFile):
            return ""
        return _xml_text(raw, members)
    return ""


def _legacy_office_text(raw: bytes) -> str:
    """Best-effort text extraction for legacy binary Office files (.doc/.xls/.ppt)."""
    unicode_chunks = re.findall(rb"(?:[\x20-\x7e\x80-\xff]\x00){4,}", raw)
    ansi_chunks = re.findall(rb"[\x20-\x7e]{8,}", raw)
    chunks = [chunk.decode("utf-16-le", errors="ignore") for chunk in unicode_chunks]
    decoded = raw.decode("utf-16-le", errors="ignore")
    chunks.extend(re.findall(r"[^\x00-\x1f]{4,}", decoded))
    chunks.extend(chunk.decode("gb18030", errors="ignore") for chunk in ansi_chunks)
    cleaned = []
    for chunk in chunks:
        text = " ".join(chunk.split())
        if text and text not in cleaned:
            cleaned.append(text)
    return "\n".join(cleaned)


def _read_submission_file(extract_dir: str, section: str, path: str) -> dict:
    section_root = pathlib.Path(os.path.realpath(os.path.join(extract_dir, section)))
    requested = pathlib.Path(os.path.realpath(os.path.join(section_root, path)))
    try:
        requested.relative_to(section_root)
    except ValueError:
        raise ApiError(404, "NOT_FOUND", "file not found")
    if not requested.exists() or not requested.is_file():
        raise ApiError(404, "NOT_FOUND", "file not found")
    try:
        raw = requested.read_bytes()
    except OSError:
        raise ApiError(404, "NOT_FOUND", "file not found")
    max_bytes = 100 * 1024
    suffix = requested.suffix.lower()
    content = raw[:max_bytes].decode("utf-8", errors="replace")
    preview_kind = "text" if suffix in _TEXT_REPORT_SUFFIXES or section == "code" else "download"
    if section == "report" and suffix in _OFFICE_REPORT_SUFFIXES:
        content = _office_report_text(raw, suffix)
        preview_kind = "office-text" if content.strip() else "download"
    elif section == "report" and suffix in _LEGACY_OFFICE_SUFFIXES:
        content = _legacy_office_text(raw)
        preview_kind = "legacy-office-text" if content.strip() else "download"
    elif section == "report" and suffix in _EMBEDDED_REPORT_SUFFIXES:
        preview_kind = "pdf"
    elif section == "report" and suffix in _SAFE_IMAGE_SUFFIXES:
        preview_kind = "image"
    return {
        "path": path,
        "content": content[:max_bytes],
        "truncated": len(raw) > max_bytes,
        "total_bytes": len(raw),
        "previewable": preview_kind != "download",
        "preview_kind": preview_kind,
    }


def _read_code_file(extract_dir: str, path: str) -> dict:
    return _read_submission_file(extract_dir, "code", path)


def _read_report_file(extract_dir: str, path: str) -> dict:
    return _read_submission_file(extract_dir, "report", path)


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


@router.get("/media/reports/{attempt_id}/{path:path}")
def report_media(
    attempt_id: int,
    path: str,
    request: Request,
    t: models.Teacher = Depends(get_teacher),
):
    """Serve report originals for browser preview or download, without exposing code files."""
    settings = request.app.state.settings
    report_root = pathlib.Path(os.path.realpath(os.path.join(settings.data_dir, "extracted", str(attempt_id), "report")))
    requested = pathlib.Path(os.path.realpath(os.path.join(report_root, path)))
    try:
        requested.relative_to(report_root)
    except ValueError:
        raise ApiError(404, "NOT_FOUND", "file not found")
    if not requested.exists() or not requested.is_file() or requested.suffix.lower() not in _REPORT_DOWNLOAD_SUFFIXES:
        raise ApiError(404, "NOT_FOUND", "file not found")
    suffix = requested.suffix.lower()
    media_type = _REPORT_MIME_TYPES.get(suffix) or mimetypes.guess_type(str(requested))[0] or "application/octet-stream"
    return FileResponse(
        str(requested),
        media_type=media_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(requested.name)}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/submissions/{sid}", response_class=HTMLResponse)
def submission_detail(
    request: Request,
    sid: int,
    file: str | None = Query(default=None),
    report: str | None = Query(default=None),
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
    report_files: list[str] = []
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
                    elif rel.startswith("report/"):
                        report_files.append(rel[7:])

    code_files.sort()
    report_files.sort()
    selected_code = None
    if attempt is not None and code_files:
        selected_code = _read_code_file(extract_dir, file or code_files[0])
    selected_report = None
    if attempt is not None and report_files:
        selected_report = _read_report_file(extract_dir, report or report_files[0])

    target_type = "individual"
    target_id = f"{submission.assignment_id}:{submission.student_id}"
    override = _current_override(db, target_type, target_id)

    final_grade = _final_grade(override, evaluation)
    ai_grade = evaluation.grade if evaluation else None
    conversations = _teacher_conversations(timelines)
    # ``metrics.user_turns`` remains an audit metric and can include synthetic
    # Codex context records. The teacher view reports only safe prompts that
    # can actually be rendered.
    display_metrics = dict(metrics)
    display_metrics["user_turns"] = sum(
        len(session["prompt_pairs"]) for session in conversations
    )

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
            "conversations": conversations,
            "metrics": display_metrics,
            "code_files": code_files,
            "code_tree": _code_tree(code_files),
            "selected_code": selected_code,
            "report_files": report_files,
            "selected_report": selected_report,
            "screenshots": screenshots,
            "media_prefix": f"/media/extracted/{attempt.id}" if attempt else "",
            "report_media_prefix": f"/media/reports/{attempt.id}" if attempt else "",
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


@router.post("/evaluations/{eid}/publish")
def publish_evaluation(
    eid: int,
    db: Session = Depends(get_db),
    t: models.Teacher = Depends(get_teacher_page),
):
    """Release the current attempt's report to its owning student."""
    evaluation = db.get(models.Evaluation, eid)
    if evaluation is None:
        raise ApiError(404, "NOT_FOUND", "评估不存在")
    attempt = db.get(models.SubmissionAttempt, evaluation.attempt_id)
    submission = db.get(models.Submission, attempt.submission_id) if attempt else None
    if attempt is None or submission is None:
        raise ApiError(404, "NOT_FOUND", "提交不存在")
    if submission.current_attempt_id != attempt.id:
        raise ApiError(409, "STALE_EVALUATION", "不能发布已被新提交替代的旧评估")
    evaluation.published_at = utcnow()
    evaluation.published_by_teacher_id = t.id
    db.commit()
    return RedirectResponse(url=f"/submissions/{submission.id}", status_code=302)


@router.post("/group-evaluations/{gid}/publish")
def publish_group_evaluation(
    gid: int,
    db: Session = Depends(get_db),
    t: models.Teacher = Depends(get_teacher_page),
):
    """Release the latest group report only to current members of that group."""
    evaluation = db.get(models.GroupEvaluation, gid)
    if evaluation is None:
        raise ApiError(404, "NOT_FOUND", "小组评估不存在")
    latest = (
        db.query(models.GroupEvaluation)
        .filter_by(assignment_id=evaluation.assignment_id, group_id=evaluation.group_id)
        .order_by(models.GroupEvaluation.generation.desc(), models.GroupEvaluation.created_at.desc())
        .first()
    )
    if latest is None or latest.id != evaluation.id:
        raise ApiError(409, "STALE_EVALUATION", "不能发布已被新版小组评估替代的旧结果")
    evaluation.published_at = utcnow()
    evaluation.published_by_teacher_id = t.id
    db.commit()
    return RedirectResponse(url=f"/assignments/{evaluation.assignment_id}/board", status_code=302)


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
