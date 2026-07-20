from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..deps import get_teacher
from ..errors import ApiError
from . import PageAuthRequired
from .board import board_data, progress_for_assignment

router = APIRouter()


def get_teacher_page(request: Request, db: Session = Depends(get_db)) -> models.Teacher:
    tid = request.session.get("teacher_id")
    if not tid:
        raise PageAuthRequired(next_url=str(request.url.path))
    t = db.get(models.Teacher, tid)
    if not t:
        raise PageAuthRequired(next_url=str(request.url.path))
    return t


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    tid = request.session.get("teacher_id")
    if not tid:
        return RedirectResponse("/login")
    teacher = db.get(models.Teacher, tid)
    if teacher is None:
        return RedirectResponse("/login")
    from ..main import templates
    courses = db.query(models.Course).all()
    assignments = db.query(models.Assignment).all()
    rows = [
        {
            "course": c,
            "assignments": [a for a in assignments if a.course_id == c.id],
        }
        for c in courses
    ]
    return templates.TemplateResponse(
        request, "dashboard.html", {"rows": rows, "teacher": teacher}
    )


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/"):
    from ..main import templates

    return templates.TemplateResponse(
        request,
        "login.html",
        {"next_url": next, "flash": ""},
    )


@router.get("/assignments/{aid}/board", response_class=HTMLResponse)
def board_page(
    request: Request,
    aid: int,
    db: Session = Depends(get_db),
    t: models.Teacher = Depends(get_teacher_page),
):
    from ..main import templates

    assignment = db.get(models.Assignment, aid)
    if assignment is None:
        raise ApiError(404, "NOT_FOUND", "作业不存在")
    data = board_data(db, assignment)
    return templates.TemplateResponse(
        request,
        "board.html",
        {
            "teacher": t,
            "assignment": data["assignment"],
            "groups": data["groups"],
            "progress": data["progress"],
        },
    )


@router.get("/api/assignments/{aid}/progress")
def progress_api(
    aid: int,
    db: Session = Depends(get_db),
    t: models.Teacher = Depends(get_teacher),
):
    if db.get(models.Assignment, aid) is None:
        raise ApiError(404, "NOT_FOUND", "作业不存在")
    return progress_for_assignment(db, aid)


@router.get("/students", response_class=HTMLResponse)
def students_page(
    request: Request,
    db: Session = Depends(get_db),
    t: models.Teacher = Depends(get_teacher_page),
):
    """Show the roster, group membership and latest submission state."""
    from ..main import templates

    courses = db.query(models.Course).order_by(models.Course.id).all()
    course_by_id = {course.id: course for course in courses}
    groups = {group.id: group.name for group in db.query(models.Group).all()}
    students = (
        db.query(models.Student)
        .order_by(models.Student.course_id, models.Student.student_no)
        .all()
    )
    statuses: dict[int, list[str]] = {}
    for submission in db.query(models.Submission).all():
        statuses.setdefault(submission.student_id, []).append(submission.status)
    rows = [
        {
            "student": student,
            "course": course_by_id.get(student.course_id),
            "group": groups.get(student.group_id, "未分组"),
            "statuses": statuses.get(student.id, []),
        }
        for student in students
    ]
    return templates.TemplateResponse(request, "students.html", {"teacher": t, "rows": rows})


@router.get("/analytics", response_class=HTMLResponse)
def analytics_page(
    request: Request,
    db: Session = Depends(get_db),
    t: models.Teacher = Depends(get_teacher_page),
):
    """Provide a small course-level summary for teachers."""
    from ..main import templates

    status_counts: dict[str, int] = {}
    grade_counts: dict[str, int] = {}
    submissions = db.query(models.Submission).all()
    for submission in submissions:
        status_counts[submission.status] = status_counts.get(submission.status, 0) + 1
    for evaluation in db.query(models.Evaluation).all():
        grade_counts[evaluation.grade] = grade_counts.get(evaluation.grade, 0) + 1
    return templates.TemplateResponse(
        request,
        "analytics.html",
        {
            "teacher": t,
            "submissions": len(submissions),
            "status_counts": status_counts,
            "grade_counts": grade_counts,
        },
    )
