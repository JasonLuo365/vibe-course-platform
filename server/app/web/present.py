import csv
import io
import json
import pathlib
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..errors import ApiError
from ..eval.metrics import compute_metrics
from ..eval.service import _parse_sessions
from .detail import _extract_dir_for_attempt, _final_grade, _latest_evaluation
from .pages import get_teacher_page

router = APIRouter()

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


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
            if p.is_file() and p.suffix.lower() in _IMAGE_SUFFIXES:
                rel = p.relative_to(extract_dir).as_posix()
                urls.append(f"/media/extracted/{attempt.id}/{rel}")
    return urls


def _group_code_highlights(
    attempts: list[models.SubmissionAttempt], settings: Any
) -> list[str]:
    """Return a compact, non-executable project file summary for projection."""
    names: list[str] = []
    seen: set[str] = set()
    for attempt in attempts:
        code_dir = pathlib.Path(_extract_dir_for_attempt(attempt, settings)) / "code"
        if not code_dir.exists():
            continue
        for path in sorted(code_dir.rglob("*")):
            if path.is_file():
                rel = path.relative_to(code_dir).as_posix()
                if rel not in seen:
                    seen.add(rel)
                    names.append(rel)
                if len(names) >= 10:
                    return names
    return names


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
        members.append(
            {
                "name": student.name,
                "student_no": student.student_no,
            }
        )
        if attempt is not None:
            attempts.append(attempt)

    return {
        "group_name": group.name if group else "未分组",
        "members": members,
        "screenshots": _group_screenshots(attempts, settings),
        "metrics": _group_metrics(attempts, settings),
        "code_highlights": _group_code_highlights(attempts, settings),
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

    return templates.TemplateResponse(
        request,
        "present.html",
        {
            "teacher": t,
            "assignment": assignment,
            "groups": groups,
        },
    )


def review_present_data(
    db: Session, assignment: models.Assignment
) -> list[dict[str, Any]]:
    """Teacher-controlled evaluation showcase, intentionally separate from work projection."""
    groups = (
        db.query(models.Group)
        .filter_by(course_id=assignment.course_id)
        .order_by(models.Group.name)
        .all()
    )
    rows: list[dict[str, Any]] = []
    group_specs: list[tuple[models.Group | None, list[models.Student]]] = []
    for group in groups:
        students = (
            db.query(models.Student)
            .filter_by(course_id=assignment.course_id, group_id=group.id)
            .order_by(models.Student.student_no)
            .all()
        )
        if students:
            group_specs.append((group, students))
    ungrouped = (
        db.query(models.Student)
        .filter_by(course_id=assignment.course_id, group_id=None)
        .order_by(models.Student.student_no)
        .all()
    )
    if ungrouped:
        group_specs.append((None, ungrouped))

    for group, students in group_specs:
        members = []
        for student in students:
            submission = (
                db.query(models.Submission)
                .filter_by(assignment_id=assignment.id, student_id=student.id)
                .first()
            )
            attempt = db.get(models.SubmissionAttempt, submission.current_attempt_id) if submission and submission.current_attempt_id else None
            evaluation = _latest_evaluation(db, attempt)
            override = _override_for_student(db, assignment.id, student.id)
            members.append(
                {
                    "name": student.name,
                    "student_no": student.student_no,
                    "status": submission.status if submission else "未提交",
                    "final_grade": _final_grade(override, evaluation),
                    "rationale": evaluation.rationale if evaluation else "",
                    "feedback": evaluation.feedback_json if evaluation else [],
                    "teacher_note": override.comment if override and not override.stale else "",
                }
            )
        geval = None
        group_override = None
        if group is not None:
            geval = (
                db.query(models.GroupEvaluation)
                .filter_by(assignment_id=assignment.id, group_id=group.id)
                .order_by(models.GroupEvaluation.created_at.desc())
                .first()
            )
            group_override = _group_override(db, assignment.id, group.id)
        rows.append(
            {
                "group_name": group.name if group else "未分组",
                "members": members,
                "group_final_grade": _final_grade(group_override, geval),
                "group_rationale": geval.rationale if geval else "",
            }
        )
    return rows


@router.get("/assignments/{aid}/review-present", response_class=HTMLResponse)
def review_present_page(
    request: Request,
    aid: int,
    db: Session = Depends(get_db),
    t: models.Teacher = Depends(get_teacher_page),
):
    from ..main import templates

    assignment = db.get(models.Assignment, aid)
    if assignment is None:
        raise ApiError(404, "NOT_FOUND", "作业不存在")
    return templates.TemplateResponse(
        request,
        "review_present.html",
        {"teacher": t, "assignment": assignment, "groups": review_present_data(db, assignment)},
    )


def _csv_row(
    db: Session,
    assignment_id: int,
    student: models.Student,
    group_name: str,
    group_evaluation: models.GroupEvaluation | None = None,
    group_override: models.GradeOverride | None = None,
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
    feedback = "\n".join(f"• {item}" for item in (evaluation.feedback_json if evaluation else []))
    group_grade = _final_grade(group_override, group_evaluation) or ""
    group_rationale = group_evaluation.rationale if group_evaluation else ""
    teacher_note = override.comment if override and not override.stale else ""
    return [
        student.student_no,
        student.name,
        group_name,
        status,
        ai_grade,
        final_grade,
        evaluation.rationale if evaluation else "",
        feedback,
        teacher_note,
        group_grade,
        group_rationale,
        dim_json,
    ]


def _safe_csv_cell(value: Any) -> str:
    """Prevent spreadsheet formula execution when feedback is opened in Excel."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(("=", "+", "-", "@")) else text


def _assignment_export_records(db: Session, assignment: models.Assignment) -> list[dict[str, Any]]:
    """Structured records used by the formatted workbook."""
    records: list[dict[str, Any]] = []
    groups = db.query(models.Group).filter_by(course_id=assignment.course_id).order_by(models.Group.name).all()
    specs: list[tuple[models.Group | None, list[models.Student]]] = []
    for group in groups:
        students = db.query(models.Student).filter_by(group_id=group.id, course_id=assignment.course_id).order_by(models.Student.student_no).all()
        if students:
            specs.append((group, students))
    ungrouped = db.query(models.Student).filter_by(course_id=assignment.course_id, group_id=None).order_by(models.Student.student_no).all()
    if ungrouped:
        specs.append((None, ungrouped))
    for group, students in specs:
        group_evaluation = None
        group_override = None
        if group:
            group_evaluation = db.query(models.GroupEvaluation).filter_by(assignment_id=assignment.id, group_id=group.id).order_by(models.GroupEvaluation.created_at.desc()).first()
            group_override = _group_override(db, assignment.id, group.id)
        for student in students:
            submission = db.query(models.Submission).filter_by(assignment_id=assignment.id, student_id=student.id).first()
            attempt = db.get(models.SubmissionAttempt, submission.current_attempt_id) if submission and submission.current_attempt_id else None
            evaluation = _latest_evaluation(db, attempt)
            records.append({
                "student": student, "group_name": group.name if group else "未分组",
                "submission": submission, "evaluation": evaluation,
                "override": _override_for_student(db, assignment.id, student.id),
                "group_evaluation": group_evaluation, "group_override": group_override,
            })
    return records


def _safe_excel_cell(value: Any) -> str:
    return _safe_csv_cell(value)


def _style_export_sheet(sheet, assignment: models.Assignment, headers: list[str], widths: list[int]) -> None:
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    title = sheet.cell(1, 1, f"Vibe 作业反馈表 · {assignment.title}")
    title.font = Font(bold=True, color="FFFFFF", size=14)
    title.fill = PatternFill("solid", fgColor="2563EB")
    title.alignment = Alignment(horizontal="left", vertical="center")
    sheet.row_dimensions[1].height = 28
    sheet.merge_cells(start_row=2, start_column=1, end_row=2, end_column=len(headers))
    sheet.cell(2, 1, f"作业码：{assignment.code}    截止时间：{assignment.deadline}")
    sheet.cell(2, 1).font = Font(color="64748B", italic=True)
    sheet.row_dimensions[2].height = 22
    for index, header in enumerate(headers, start=1):
        cell = sheet.cell(4, index, header)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1D4ED8")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        sheet.column_dimensions[get_column_letter(index)].width = widths[index - 1]
    sheet.row_dimensions[4].height = 26
    sheet.freeze_panes = "A5"
    sheet.auto_filter.ref = f"A4:{get_column_letter(len(headers))}4"
    sheet.sheet_view.showGridLines = False


def _write_export_row(sheet, row_index: int, values: list[Any]) -> None:
    for column, value in enumerate(values, start=1):
        cell = sheet.cell(row_index, column, _safe_excel_cell(value))
        cell.alignment = Alignment(vertical="top", wrap_text=True)
    if row_index % 2:
        for cell in sheet[row_index]:
            cell.fill = PatternFill("solid", fgColor="F8FAFC")


@router.get("/assignments/{aid}/export.xlsx")
def export_xlsx(request: Request, aid: int, db: Session = Depends(get_db), t: models.Teacher = Depends(get_teacher_page)):
    assignment = db.get(models.Assignment, aid)
    if assignment is None:
        raise ApiError(404, "NOT_FOUND", "作业不存在")
    records = _assignment_export_records(db, assignment)
    workbook = Workbook()
    overview = workbook.active
    overview.title = "反馈总表"
    _style_export_sheet(overview, assignment, ["学号", "姓名", "小组", "提交状态", "AI 等级", "最终等级", "教师备注"], [15, 14, 14, 14, 11, 11, 30])
    for index, record in enumerate(records, start=5):
        submission, evaluation, override = record["submission"], record["evaluation"], record["override"]
        _write_export_row(overview, index, [record["student"].student_no, record["student"].name, record["group_name"], submission.status if submission else "未提交", evaluation.grade if evaluation else "", _final_grade(override, evaluation) or "", override.comment if override and not override.stale else ""])

    feedback = workbook.create_sheet("个人反馈")
    _style_export_sheet(feedback, assignment, ["学号", "姓名", "小组", "个人评价", "改进建议"], [15, 14, 14, 52, 52])
    for index, record in enumerate(records, start=5):
        evaluation = record["evaluation"]
        improvements = "\n".join(f"• {item}" for item in (evaluation.feedback_json if evaluation else []))
        _write_export_row(feedback, index, [record["student"].student_no, record["student"].name, record["group_name"], evaluation.rationale if evaluation else "", improvements])
        feedback.row_dimensions[index].height = 90

    dimensions = workbook.create_sheet("评分维度")
    _style_export_sheet(dimensions, assignment, ["学号", "姓名", "小组", "评分维度", "得分", "权重", "评分说明"], [15, 14, 14, 20, 10, 10, 60])
    row = 5
    for record in records:
        evaluation = record["evaluation"]
        for dimension in (evaluation.dimension_scores_json if evaluation else []):
            if isinstance(dimension, dict):
                _write_export_row(dimensions, row, [record["student"].student_no, record["student"].name, record["group_name"], dimension.get("name", ""), dimension.get("score", ""), dimension.get("weight", ""), dimension.get("rationale", "")])
                dimensions.row_dimensions[row].height = 48
                row += 1

    groups = workbook.create_sheet("小组反馈")
    _style_export_sheet(groups, assignment, ["小组", "最终等级", "小组评价"], [20, 12, 80])
    seen: set[str] = set()
    row = 5
    for record in records:
        if record["group_name"] in seen:
            continue
        seen.add(record["group_name"])
        group_evaluation = record["group_evaluation"]
        _write_export_row(groups, row, [record["group_name"], _final_grade(record["group_override"], group_evaluation) or "", group_evaluation.rationale if group_evaluation else ""])
        groups.row_dimensions[row].height = 72
        row += 1

    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": 'attachment; filename="vibe-feedback.xlsx"'})


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
    writer.writerow([
        "学号", "姓名", "小组", "提交状态", "AI等级", "最终等级",
        "个人评价", "个人改进建议", "教师备注", "小组最终等级", "小组评价", "各维度分(json)",
    ])

    groups = (
        db.query(models.Group)
        .filter_by(course_id=assignment.course_id)
        .order_by(models.Group.name)
        .all()
    )
    for group in groups:
        group_evaluation = (
            db.query(models.GroupEvaluation)
            .filter_by(assignment_id=assignment.id, group_id=group.id)
            .order_by(models.GroupEvaluation.created_at.desc())
            .first()
        )
        group_override = _group_override(db, assignment.id, group.id)
        students = (
            db.query(models.Student)
            .filter_by(group_id=group.id, course_id=assignment.course_id)
            .order_by(models.Student.student_no)
            .all()
        )
        for student in students:
            writer.writerow([
                _safe_csv_cell(cell)
                for cell in _csv_row(
                    db, assignment.id, student, group.name, group_evaluation, group_override
                )
            ])

    ungrouped = (
        db.query(models.Student)
        .filter_by(course_id=assignment.course_id, group_id=None)
        .order_by(models.Student.student_no)
        .all()
    )
    for student in ungrouped:
        writer.writerow([_safe_csv_cell(cell) for cell in _csv_row(db, assignment.id, student, "未分组")])

    content = output.getvalue()
    encoded = content.encode("utf-8")
    return StreamingResponse(
        io.BytesIO(encoded),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="export.csv"'},
    )
