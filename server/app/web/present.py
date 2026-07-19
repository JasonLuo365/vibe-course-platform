import csv
import io
import json
import pathlib
import re
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..errors import ApiError
from ..eval.metrics import compute_metrics
from ..eval.service import _parse_sessions
from .detail import _extract_dir_for_attempt, _final_grade, _latest_evaluation
from .pages import get_teacher_page

router = APIRouter()

_FORBIDDEN_PRESENT_KEYS = {"dimension_scores", "feedback", "flags", "evidence"}


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


def _group_override(db: Session, assignment_id: int, group_id: int):
    return (
        db.query(models.GradeOverride)
        .filter_by(
            target_type="group",
            target_id=f"{assignment_id}:{group_id}",
        )
        .order_by(models.GradeOverride.updated_at.desc())
        .first()
    )


def _rationale_head(text: str | None, max_sentences: int = 3) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    sentences = re.findall(r"[^。\.\!\?]+[。\.\!\?]*", text)
    if not sentences:
        return text[:160]
    return "".join(sentences[:max_sentences]).strip()


def _sanitize_contribution(obj: Any) -> Any:
    """Remove per-dimension / feedback / flags / evidence data from embedded JSON."""
    if isinstance(obj, dict):
        return {
            k: _sanitize_contribution(v)
            for k, v in obj.items()
            if k not in _FORBIDDEN_PRESENT_KEYS
        }
    if isinstance(obj, list):
        return [_sanitize_contribution(v) for v in obj]
    return obj


def _group_screenshots(
    attempts: list[models.SubmissionAttempt], settings: Any
) -> list[str]:
    urls: list[str] = []
    for attempt in attempts:
        extract_dir = pathlib.Path(_extract_dir_for_attempt(attempt, settings))
        screenshots_dir = extract_dir / "screenshots"
        if not screenshots_dir.exists():
            continue
        for p in sorted(screenshots_dir.iterdir()):
            if p.is_file():
                rel = p.relative_to(extract_dir).as_posix()
                urls.append(f"/media/extracted/{attempt.id}/{rel}")
    return urls


def _group_metrics(
    attempts: list[models.SubmissionAttempt], settings: Any
) -> dict[str, Any]:
    all_timelines: list[Any] = []
    for attempt in attempts:
        extract_dir = _extract_dir_for_attempt(attempt, settings)
        all_timelines.extend(_parse_sessions(extract_dir))
    metrics = compute_metrics(all_timelines)
    return {
        "sessions": metrics.get("sessions", 0),
        "turns": metrics.get("turns", 0),
        "duration_min": metrics.get("duration_min", 0),
    }


def _member_final_grade(
    db: Session, assignment_id: int, student_id: int, attempt
) -> str | None:
    evaluation = _latest_evaluation(db, attempt)
    override = _override_for_student(db, assignment_id, student_id)
    return _final_grade(override, evaluation)


def _build_group_row(
    db: Session,
    assignment: models.Assignment,
    group: models.Group | None,
    students: list[models.Student],
    settings: Any,
) -> dict[str, Any]:
    members: list[dict[str, Any]] = []
    attempts: list[models.SubmissionAttempt] = []
    for student in students:
        submission = (
            db.query(models.Submission)
            .filter_by(assignment_id=assignment.id, student_id=student.id)
            .first()
        )
        attempt = None
        if submission is not None and submission.current_attempt_id is not None:
            attempt = db.get(models.SubmissionAttempt, submission.current_attempt_id)
        final_grade = _member_final_grade(db, assignment.id, student.id, attempt)
        members.append(
            {
                "name": student.name,
                "student_no": student.student_no,
                "final_grade": final_grade,
                "status": submission.status if submission else "none",
            }
        )
        if attempt is not None:
            attempts.append(attempt)

    highlight = None
    if group is not None:
        geval = (
            db.query(models.GroupEvaluation)
            .filter_by(assignment_id=assignment.id, group_id=group.id)
            .order_by(models.GroupEvaluation.created_at.desc())
            .first()
        )
        if geval is not None:
            group_override = _group_override(db, assignment.id, group.id)
            final_group_grade = _final_grade(group_override, geval)
            highlight = {
                "grade": geval.grade,
                "final_grade": final_group_grade,
                "rationale_head": _rationale_head(geval.rationale),
                "contribution_json": _sanitize_contribution(geval.contribution_json),
            }

    return {
        "group_name": group.name if group else "未分组",
        "members": members,
        "highlight": highlight,
        "screenshots": _group_screenshots(attempts, settings),
        "metrics": _group_metrics(attempts, settings),
    }


def present_data(db: Session, assignment: models.Assignment, settings: Any) -> list[dict[str, Any]]:
    groups = (
        db.query(models.Group)
        .filter_by(course_id=assignment.course_id)
        .order_by(models.Group.name)
        .all()
    )

    rows: list[dict[str, Any]] = []
    for group in groups:
        students = (
            db.query(models.Student)
            .filter_by(group_id=group.id, course_id=assignment.course_id)
            .order_by(models.Student.student_no)
            .all()
        )
        if students:
            rows.append(_build_group_row(db, assignment, group, students, settings))

    ungrouped = (
        db.query(models.Student)
        .filter_by(course_id=assignment.course_id, group_id=None)
        .order_by(models.Student.student_no)
        .all()
    )
    if ungrouped:
        rows.append(
            _build_group_row(db, assignment, None, ungrouped, settings)
        )

    return rows


@router.get("/assignments/{aid}/present", response_class=HTMLResponse)
def present_page(
    request: Request,
    aid: int,
    db: Session = Depends(get_db),
    t: models.Teacher = Depends(get_teacher_page),
):
    from ..main import templates

    assignment = db.get(models.Assignment, aid)
    if assignment is None:
        raise ApiError(404, "NOT_FOUND", "作业不存在")

    settings = request.app.state.settings
    groups = present_data(db, assignment, settings)
    groups_json = json.dumps(groups, ensure_ascii=False)

    return templates.TemplateResponse(
        request,
        "present.html",
        {
            "teacher": t,
            "assignment": assignment,
            "groups_json": groups_json,
        },
    )


def _csv_row(
    db: Session,
    assignment_id: int,
    student: models.Student,
    group_name: str,
) -> list[str]:
    submission = (
        db.query(models.Submission)
        .filter_by(assignment_id=assignment_id, student_id=student.id)
        .first()
    )
    attempt = None
    if submission is not None and submission.current_attempt_id is not None:
        attempt = db.get(models.SubmissionAttempt, submission.current_attempt_id)
    evaluation = _latest_evaluation(db, attempt)
    override = _override_for_student(db, assignment_id, student.id)

    ai_grade = evaluation.grade if evaluation else ""
    final_grade = _final_grade(override, evaluation) or ""

    dims: dict[str, Any] = {}
    if evaluation is not None and evaluation.dimension_scores_json:
        for d in evaluation.dimension_scores_json:
            if isinstance(d, dict) and "name" in d and "score" in d:
                dims[d["name"]] = d["score"]
    dim_json = json.dumps(dims, ensure_ascii=False, separators=(",", ":")) if dims else ""

    status = submission.status if submission else "none"
    return [
        student.student_no,
        student.name,
        group_name,
        ai_grade,
        final_grade,
        dim_json,
        status,
    ]


@router.get("/assignments/{aid}/export.csv")
def export_csv(
    request: Request,
    aid: int,
    db: Session = Depends(get_db),
    t: models.Teacher = Depends(get_teacher_page),
):
    assignment = db.get(models.Assignment, aid)
    if assignment is None:
        raise ApiError(404, "NOT_FOUND", "作业不存在")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["学号", "姓名", "小组", "AI等级", "最终等级", "各维度分(json)", "提交状态"])

    groups = (
        db.query(models.Group)
        .filter_by(course_id=assignment.course_id)
        .order_by(models.Group.name)
        .all()
    )
    for group in groups:
        students = (
            db.query(models.Student)
            .filter_by(group_id=group.id, course_id=assignment.course_id)
            .order_by(models.Student.student_no)
            .all()
        )
        for student in students:
            writer.writerow(_csv_row(db, assignment.id, student, group.name))

    ungrouped = (
        db.query(models.Student)
        .filter_by(course_id=assignment.course_id, group_id=None)
        .order_by(models.Student.student_no)
        .all()
    )
    for student in ungrouped:
        writer.writerow(_csv_row(db, assignment.id, student, "未分组"))

    content = output.getvalue()
    encoded = content.encode("utf-8")
    return StreamingResponse(
        io.BytesIO(encoded),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="export.csv"'},
    )
