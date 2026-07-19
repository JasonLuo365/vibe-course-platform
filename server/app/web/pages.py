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
        request, "dashboard.html", {"rows": rows}
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
